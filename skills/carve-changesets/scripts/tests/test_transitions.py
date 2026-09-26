from __future__ import annotations

import unittest
from dataclasses import replace

import helpers  # noqa: F401  # ensures the scripts directory is importable
from gh_stack import StackCapability, reviewed_preview_profile
from transitions import (
    ZERO_SHA,
    AuthorityGrant,
    EffectKind,
    ExpectedNativeLayer,
    ExpectedNativeStack,
    ExpectedPullRequest,
    ExpectedRef,
    ManifestError,
    MergeMode,
    MutationEffect,
    MutationManifest,
    StackOperation,
    TargetDisposition,
    TransitionObservation,
    TransitionPhase,
    TransitionState,
    classify_readback,
    execute_transition,
    manifest_from_json,
    manifest_to_json,
    observation_from_manifest,
    preview_merge,
    preview_publish,
    preview_recovery,
    preview_repair,
    required_capabilities,
)

SHA_A = "a" * 40
SHA_B = "b" * 40
SHA_C = "c" * 40
SHA_D = "d" * 40


def publish_manifest() -> MutationManifest:
    refs = (
        ExpectedRef("refs/heads/feature-1", SHA_A, SHA_C),
        ExpectedRef("refs/heads/feature-2", ZERO_SHA, SHA_D),
    )
    pull_requests = (
        ExpectedPullRequest(
            number=41,
            branch="feature-1",
            head=SHA_A,
            base="main",
            state="OPEN",
            draft=False,
            queued=False,
            auto_merge=True,
            title="Add transition model",
            body="Layer one body",
        ),
        ExpectedPullRequest(
            number=None,
            branch="feature-2",
            head=None,
            base=None,
            state="ABSENT",
            draft=None,
            queued=None,
            auto_merge=None,
            title="Integrate transition model",
            body="Layer two body",
        ),
    )
    stack = ExpectedNativeStack(
        identity="stack-9",
        registered=False,
        trunk="main",
        trunk_head=SHA_A,
        layers=(
            ExpectedNativeLayer(
                branch="feature-1",
                head=SHA_A,
                base=SHA_A,
                merged=False,
                queued=False,
                needs_rebase=False,
                pull_request=41,
                pull_request_state="OPEN",
            ),
            ExpectedNativeLayer(
                branch="feature-2",
                head=SHA_B,
                base=SHA_A,
                merged=False,
                queued=False,
                needs_rebase=False,
                pull_request=None,
                pull_request_state=None,
            ),
        ),
    )
    return preview_publish(
        repository="shaug/compris",
        remote="origin",
        refs=refs,
        pull_requests=pull_requests,
        native_stack=stack,
        authority=AuthorityGrant.publish(
            repository="shaug/compris",
            remote="origin",
            branches=("feature-1", "feature-2"),
            pull_requests=pull_requests,
        ),
        evidence=("native stack snapshot 9", "GitHub PR snapshot 12"),
    )


class PublishManifestTests(unittest.TestCase):
    def test_manifest_json_round_trip_preserves_every_fenced_input(self) -> None:
        manifest = publish_manifest()

        restored = manifest_from_json(manifest_to_json(manifest))

        self.assertEqual(manifest, restored)

    def test_manifest_json_rejects_string_boolean_pr_state(self) -> None:
        payload = __import__("json").loads(manifest_to_json(publish_manifest()))
        payload["expected_pull_requests"][0]["draft"] = "false"

        with self.assertRaisesRegex(ManifestError, "draft.*boolean"):
            manifest_from_json(__import__("json").dumps(payload))

    def test_preview_enumerates_direct_and_automatic_effects(self) -> None:
        manifest = publish_manifest()

        self.assertEqual(
            tuple(effect.kind for effect in manifest.effects),
            (
                EffectKind.PUSH_REF,
                EffectKind.PUSH_REF,
                EffectKind.UPDATE_PR,
                EffectKind.CREATE_PR,
                EffectKind.DISABLE_AUTO_MERGE,
                EffectKind.REGISTER_STACK,
            ),
        )
        self.assertEqual(SHA_A, manifest.expected_refs[0].old_sha)
        self.assertEqual(ZERO_SHA, manifest.expected_refs[1].old_sha)
        self.assertEqual("ABSENT", manifest.expected_pull_requests[1].state)
        self.assertEqual(
            ("feature-1", "feature-2"), manifest.expected_native_stack.order
        )
        registration = next(
            effect
            for effect in manifest.effects
            if effect.kind is EffectKind.REGISTER_STACK
        )
        self.assertIsNone(registration.before)
        self.assertEqual("stack-9", registration.after)
        created = next(
            effect for effect in manifest.effects if effect.kind is EffectKind.CREATE_PR
        )
        self.assertTrue(created.after[5], "new pull requests default to draft")

    def test_ready_for_review_requires_distinct_branch_authority(self) -> None:
        manifest = publish_manifest()
        grant = replace(
            manifest.authority,
            ready_for_review=("feature-2",),
            effect_kinds=manifest.authority.effect_kinds
            | frozenset({EffectKind.READY_PR}),
        )

        ready = preview_publish(
            repository=manifest.repository,
            remote=manifest.remote,
            refs=manifest.expected_refs,
            pull_requests=manifest.expected_pull_requests,
            native_stack=manifest.expected_native_stack,
            authority=grant,
            evidence=manifest.evidence,
        )

        created = next(
            effect for effect in ready.effects if effect.kind is EffectKind.CREATE_PR
        )
        self.assertFalse(created.after[5])

    def test_created_pr_readback_accepts_only_the_assigned_identity(self) -> None:
        approved = publish_manifest()
        current_pull_requests = (
            approved.expected_pull_requests[0],
            ExpectedPullRequest(
                number=52,
                branch="feature-2",
                head=SHA_D,
                base="feature-1",
                state="OPEN",
                draft=True,
                queued=False,
                auto_merge=False,
                title="Integrate transition model",
                body="Layer two body",
                current_title="Integrate transition model",
                current_body="Layer two body",
            ),
        )
        current = preview_publish(
            repository=approved.repository,
            remote=approved.remote,
            refs=approved.expected_refs,
            pull_requests=current_pull_requests,
            native_stack=replace(approved.expected_native_stack, registered=True),
            authority=AuthorityGrant.publish(
                repository=approved.repository,
                remote=approved.remote,
                branches=("feature-1", "feature-2"),
                pull_requests=current_pull_requests,
            ),
            evidence=approved.evidence,
        )

        result = classify_readback(
            approved, observation_from_manifest(approved, current)
        )
        created = next(
            target
            for target in result.targets
            if target.effect.kind is EffectKind.CREATE_PR
        )

        self.assertEqual(TargetDisposition.CHANGED_AS_EXPECTED, created.disposition)
        self.assertEqual(52, created.observed[0])

    def test_publish_binds_live_pr_text_separately_from_proposed_text(self) -> None:
        manifest = publish_manifest()
        current = replace(
            manifest.expected_pull_requests[0],
            current_title="Old layer title",
            current_body="Old layer body",
        )
        rebuilt = preview_publish(
            repository=manifest.repository,
            remote=manifest.remote,
            refs=manifest.expected_refs,
            pull_requests=(current, manifest.expected_pull_requests[1]),
            native_stack=manifest.expected_native_stack,
            authority=manifest.authority,
            evidence=manifest.evidence,
        )
        update = next(
            effect for effect in rebuilt.effects if effect.kind is EffectKind.UPDATE_PR
        )

        self.assertIn("Old layer title", update.before)
        self.assertIn("Old layer body", update.before)
        self.assertIn("Add transition model", update.after)
        self.assertIn("Layer one body", update.after)

    def test_publish_requires_an_explicit_body_for_every_layer(self) -> None:
        manifest = publish_manifest()
        pull_requests = list(manifest.expected_pull_requests)
        pull_requests[1] = replace(pull_requests[1], body="")

        with self.assertRaisesRegex(ManifestError, "explicit pull-request body"):
            replace(
                manifest, expected_pull_requests=tuple(pull_requests)
            ).validate_complete()

    def test_authority_must_cover_every_effect_and_enabled_phase(self) -> None:
        manifest = publish_manifest()
        incomplete = replace(
            manifest.authority,
            effect_kinds=frozenset({EffectKind.PUSH_REF}),
            phases=frozenset({TransitionPhase.PUSH}),
        )

        with self.assertRaisesRegex(ManifestError, "exactly match"):
            replace(manifest, authority=incomplete).validate_complete()

    def test_authority_must_not_grant_effects_beyond_the_manifest(self) -> None:
        manifest = publish_manifest()
        overbroad = replace(
            manifest.authority,
            effect_kinds=manifest.authority.effect_kinds
            | frozenset({EffectKind.READY_PR}),
        )

        with self.assertRaisesRegex(ManifestError, "exactly match"):
            replace(manifest, authority=overbroad).validate_complete()

    def test_authority_must_cover_every_mutated_branch(self) -> None:
        manifest = publish_manifest()
        incomplete = replace(
            manifest.authority,
            branches=("feature-1",),
        )

        with self.assertRaisesRegex(ManifestError, "exactly match"):
            replace(manifest, authority=incomplete).validate_complete()

    def test_manifest_rejects_an_omitted_declared_resource_effect(self) -> None:
        manifest = publish_manifest()
        incomplete = replace(
            manifest,
            effects=tuple(
                effect
                for effect in manifest.effects
                if effect.target != "ref:feature-2"
            ),
        )

        with self.assertRaisesRegex(ManifestError, "missing required effect"):
            incomplete.validate_complete()


class CapabilityFenceTests(unittest.TestCase):
    def test_missing_authority_returns_blocked_before_executor_invocation(self) -> None:
        manifest = publish_manifest()
        incomplete = replace(
            manifest,
            authority=replace(
                manifest.authority,
                effect_kinds=frozenset({EffectKind.PUSH_REF}),
            ),
        )
        calls: list[MutationManifest] = []

        result = execute_transition(
            incomplete,
            profile=reviewed_preview_profile(
                "14fc42ed9b6c376a53b2f999f138d3bd26dac546"
            ),
            reread=lambda: incomplete,
            executor=lambda approved: calls.append(approved),
            readback=lambda: TransitionObservation.from_manifest_before(incomplete),
        )

        self.assertEqual(TransitionState.BLOCKED, result.state)
        self.assertIn("authority grant must exactly match", result.blocker)
        self.assertEqual([], calls)

    def test_invalid_pre_execution_reread_returns_blocked(self) -> None:
        manifest = publish_manifest()
        profile = replace(
            reviewed_preview_profile("14fc42ed9b6c376a53b2f999f138d3bd26dac546"),
            capabilities=required_capabilities(
                manifest.operation,
                phases=manifest.enabled_phases,
                merge_mode=manifest.merge_mode,
            ),
        )
        invalid = replace(
            manifest,
            authority=replace(manifest.authority, identities=()),
        )

        result = execute_transition(
            manifest,
            profile=profile,
            reread=lambda: invalid,
            executor=lambda _approved: self.fail("executor must remain fenced"),
            readback=lambda: TransitionObservation.from_manifest_before(manifest),
        )

        self.assertEqual(TransitionState.BLOCKED, result.state)
        self.assertIn("pre-execution reread is invalid", result.blocker)

    def test_executor_failure_still_classifies_partial_remote_effects(self) -> None:
        manifest = publish_manifest()
        profile = replace(
            reviewed_preview_profile("14fc42ed9b6c376a53b2f999f138d3bd26dac546"),
            capabilities=required_capabilities(
                manifest.operation,
                phases=manifest.enabled_phases,
                merge_mode=manifest.merge_mode,
            ),
        )
        first, *remaining = manifest.effects
        observation = TransitionObservation(
            values=(
                (first.key, first.after),
                *((effect.key, effect.before) for effect in remaining),
            )
        )

        def fail_after_first(_approved: MutationManifest) -> None:
            raise RuntimeError("second lease rejected")

        result = execute_transition(
            manifest,
            profile=profile,
            reread=lambda: manifest,
            executor=fail_after_first,
            readback=lambda: observation,
        )

        self.assertEqual(TransitionState.PARTIAL, result.state)
        self.assertIn("second lease rejected", result.blocker)
        self.assertTrue(result.fresh_manifest_required)

    def test_successful_executor_with_partial_readback_returns_blocked(self) -> None:
        manifest = publish_manifest()
        profile = replace(
            reviewed_preview_profile("14fc42ed9b6c376a53b2f999f138d3bd26dac546"),
            capabilities=required_capabilities(
                manifest.operation,
                phases=manifest.enabled_phases,
                merge_mode=manifest.merge_mode,
            ),
        )
        first, *remaining = manifest.effects
        observation = TransitionObservation(
            values=(
                (first.key, first.after),
                *((effect.key, effect.before) for effect in remaining),
            )
        )

        result = execute_transition(
            manifest,
            profile=profile,
            reread=lambda: manifest,
            executor=lambda _approved: None,
            readback=lambda: observation,
        )

        self.assertEqual(TransitionState.BLOCKED, result.state)
        self.assertTrue(result.fresh_manifest_required)

    def test_successful_executor_with_every_pending_write_unchanged_is_blocked(
        self,
    ) -> None:
        manifest = publish_manifest()

        result = execute_transition(
            manifest,
            profile=__import__("gh_stack").GhStackProfile(
                version="test-complete",
                source_revision="test",
                capabilities=frozenset(StackCapability),
            ),
            reread=lambda: manifest,
            executor=lambda _approved: None,
            readback=lambda: TransitionObservation.from_manifest_before(manifest),
        )

        self.assertEqual(TransitionState.BLOCKED, result.state)
        self.assertIn("pending", result.blocker)

    def test_reviewed_profile_blocks_before_executor_invocation(self) -> None:
        manifest = publish_manifest()
        calls: list[MutationManifest] = []
        rereads: list[MutationManifest] = []

        def reread() -> MutationManifest:
            rereads.append(manifest)
            return manifest

        result = execute_transition(
            manifest,
            profile=reviewed_preview_profile(
                "14fc42ed9b6c376a53b2f999f138d3bd26dac546"
            ),
            reread=reread,
            executor=lambda approved: calls.append(approved),
            readback=lambda: TransitionObservation.from_manifest_before(manifest),
        )

        self.assertEqual(TransitionState.BLOCKED, result.state)
        self.assertIn("explicit_pull_request_bodies", result.blocker)
        self.assertEqual([], rereads)
        self.assertEqual([], calls)
        self.assertEqual(manifest, result.retained_manifest)


class OperationManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.refs = (
            ExpectedRef("refs/heads/feature-2", SHA_A, SHA_C),
            ExpectedRef("refs/heads/feature-3", SHA_B, SHA_D),
        )
        self.pull_requests = (
            ExpectedPullRequest(
                number=42,
                branch="feature-2",
                head=SHA_A,
                base="main",
                state="OPEN",
                draft=False,
                queued=False,
                auto_merge=False,
                merge_state_status="CLEAN",
                title="Layer 2",
                body="Layer 2 body",
            ),
            ExpectedPullRequest(
                number=43,
                branch="feature-3",
                head=SHA_B,
                base="feature-2",
                state="OPEN",
                draft=False,
                queued=False,
                auto_merge=False,
                merge_state_status="CLEAN",
                title="Layer 3",
                body="Layer 3 body",
            ),
        )
        self.stack = ExpectedNativeStack(
            identity="stack-9",
            registered=True,
            trunk="main",
            trunk_head=SHA_A,
            layers=(
                ExpectedNativeLayer(
                    branch="feature-2",
                    head=SHA_A,
                    base=SHA_A,
                    merged=False,
                    queued=False,
                    needs_rebase=False,
                    pull_request=42,
                    pull_request_state="OPEN",
                ),
                ExpectedNativeLayer(
                    branch="feature-3",
                    head=SHA_B,
                    base=SHA_A,
                    merged=False,
                    queued=False,
                    needs_rebase=False,
                    pull_request=43,
                    pull_request_state="OPEN",
                ),
            ),
        )

    def _authority(
        self,
        operation: StackOperation,
        phases: frozenset[TransitionPhase],
        effects: frozenset[EffectKind],
        merge_method: str | None = None,
    ) -> AuthorityGrant:
        identities = ("feature-2", "feature-3")
        return AuthorityGrant(
            operation=operation,
            repository="shaug/compris",
            remote="origin",
            identities=identities,
            branches=(
                (*identities, "main")
                if operation is StackOperation.MERGE
                else identities
            ),
            phases=phases,
            effect_kinds=effects,
            merge_method=merge_method,
        )

    def test_repair_fences_rebase_push_pr_and_stack_sync_independently(self) -> None:
        phases = frozenset(
            {
                TransitionPhase.REBASE_NO_TRUNK,
                TransitionPhase.PUSH,
                TransitionPhase.SYNC,
            }
        )
        manifest = preview_repair(
            repository="shaug/compris",
            remote="origin",
            refs=self.refs,
            pull_requests=self.pull_requests,
            native_stack=self.stack,
            authority=self._authority(
                StackOperation.REPAIR,
                phases,
                frozenset(
                    {
                        EffectKind.REBASE_BRANCH,
                        EffectKind.PUSH_REF,
                        EffectKind.UPDATE_PR,
                        EffectKind.SYNC_STACK,
                    }
                ),
            ),
            evidence=("repair snapshot",),
        )

        self.assertEqual(
            (
                TransitionPhase.REBASE_NO_TRUNK,
                TransitionPhase.PUSH,
                TransitionPhase.SYNC,
            ),
            manifest.enabled_phases,
        )
        self.assertEqual(
            (
                EffectKind.REBASE_BRANCH,
                EffectKind.REBASE_BRANCH,
                EffectKind.PUSH_REF,
                EffectKind.PUSH_REF,
                EffectKind.UPDATE_PR,
                EffectKind.UPDATE_PR,
                EffectKind.SYNC_STACK,
            ),
            tuple(effect.kind for effect in manifest.effects),
        )

    def test_direct_merge_binds_prefix_and_automatic_suffix_effects(self) -> None:
        phases = frozenset({TransitionPhase.DIRECT_MERGE, TransitionPhase.SYNC})
        manifest = preview_merge(
            repository="shaug/compris",
            remote="origin",
            refs=self.refs,
            pull_requests=self.pull_requests,
            native_stack=self.stack,
            prefix_numbers=(42,),
            merge_mode=MergeMode.DIRECT,
            merge_method="merge",
            trunk_tree_before=SHA_A,
            trunk_tree_after=SHA_B,
            authority=self._authority(
                StackOperation.MERGE,
                phases,
                frozenset(
                    {
                        EffectKind.MERGE_PR,
                        EffectKind.REFRESH_TRUNK,
                        EffectKind.PUSH_REF,
                        EffectKind.UPDATE_PR,
                        EffectKind.SYNC_STACK,
                    }
                ),
                merge_method="merge",
            ),
            evidence=("merge snapshot",),
        )

        self.assertEqual(
            (
                EffectKind.MERGE_PR,
                EffectKind.REFRESH_TRUNK,
                EffectKind.SYNC_STACK,
                EffectKind.PUSH_REF,
                EffectKind.UPDATE_PR,
                EffectKind.SYNC_STACK,
            ),
            tuple(effect.kind for effect in manifest.effects),
        )
        self.assertEqual((42,), manifest.merge_prefix)
        payload = __import__("json").loads(manifest_to_json(manifest))
        self.assertEqual("merge", payload["merge_method"])
        self.assertEqual("merge", payload["authority"]["merge_method"])
        self.assertEqual(
            manifest, manifest_from_json(__import__("json").dumps(payload))
        )

    def test_queue_merge_admits_only_the_bottom_pr_and_fences_landing(self) -> None:
        phases = frozenset({TransitionPhase.QUEUE_MERGE})
        manifest = preview_merge(
            repository="shaug/compris",
            remote="origin",
            refs=self.refs,
            pull_requests=self.pull_requests,
            native_stack=self.stack,
            prefix_numbers=(42,),
            merge_mode=MergeMode.QUEUE,
            merge_method=None,
            trunk_tree_before=SHA_A,
            trunk_tree_after=SHA_B,
            authority=self._authority(
                StackOperation.MERGE,
                phases,
                frozenset(
                    {
                        EffectKind.QUEUE_PR,
                        EffectKind.MERGE_PR,
                        EffectKind.REFRESH_TRUNK,
                        EffectKind.PUSH_REF,
                        EffectKind.UPDATE_PR,
                        EffectKind.SYNC_STACK,
                    }
                ),
            ),
            evidence=("queue snapshot",),
        )

        self.assertEqual(
            (
                EffectKind.QUEUE_PR,
                EffectKind.MERGE_PR,
                EffectKind.REFRESH_TRUNK,
                EffectKind.SYNC_STACK,
                EffectKind.PUSH_REF,
                EffectKind.UPDATE_PR,
                EffectKind.SYNC_STACK,
            ),
            tuple(effect.kind for effect in manifest.effects),
        )
        self.assertEqual("pr:42", manifest.effects[0].target)
        self.assertEqual("pr:42", manifest.effects[1].target)
        payload = __import__("json").loads(manifest_to_json(manifest))
        self.assertIsNone(payload["merge_method"])
        self.assertIsNone(payload["authority"]["merge_method"])

        admission = classify_readback(
            manifest,
            TransitionObservation(
                values=tuple(
                    (
                        effect.key,
                        True if effect.kind is EffectKind.QUEUE_PR else effect.before,
                    )
                    for effect in manifest.effects
                )
            ),
        )
        self.assertEqual(TransitionState.ADMITTED, admission.state)
        self.assertIs(manifest, admission.retained_manifest)
        self.assertIn("do not admit", admission.next_action)

        landing = classify_readback(
            manifest,
            TransitionObservation(
                values=tuple(
                    (
                        effect.key,
                        effect.before
                        if effect.kind is EffectKind.QUEUE_PR
                        else effect.after,
                    )
                    for effect in manifest.effects
                )
            ),
        )
        self.assertEqual(TransitionState.COMPLETED, landing.state)

        for field in ("tree", "open_order"):
            with self.subTest(field=field):
                drift_values = [
                    (
                        effect.key,
                        (
                            "f" * 40
                            if effect.field == field and field == "tree"
                            else ("unexpected-layer",)
                            if effect.field == field
                            else effect.after
                        ),
                    )
                    for effect in manifest.effects
                ]
                drift = classify_readback(
                    manifest,
                    TransitionObservation(values=tuple(drift_values)),
                )
                self.assertEqual(TransitionState.DIVERGED, drift.state)

        cancelled = classify_readback(
            manifest,
            TransitionObservation.from_manifest_before(manifest),
        )
        self.assertEqual(TransitionState.PARTIAL, cancelled.state)

        drift_values = list(TransitionObservation.from_manifest_before(manifest).values)
        drift_values[-1] = (drift_values[-1][0], "e" * 40)
        drift = classify_readback(
            manifest,
            TransitionObservation(values=tuple(drift_values)),
        )
        self.assertEqual(TransitionState.DIVERGED, drift.state)

    def test_direct_full_prefix_does_not_claim_a_suffix_sync(self) -> None:
        phases = frozenset({TransitionPhase.DIRECT_MERGE})
        manifest = preview_merge(
            repository="shaug/compris",
            remote="origin",
            pull_requests=self.pull_requests,
            native_stack=self.stack,
            prefix_numbers=(42, 43),
            merge_mode=MergeMode.DIRECT,
            merge_method="squash",
            trunk_tree_before=SHA_A,
            trunk_tree_after=SHA_B,
            authority=self._authority(
                StackOperation.MERGE,
                phases,
                frozenset(
                    {
                        EffectKind.MERGE_PR,
                        EffectKind.REFRESH_TRUNK,
                        EffectKind.SYNC_STACK,
                    }
                ),
                merge_method="squash",
            ),
            evidence=("merge snapshot",),
        )

        self.assertEqual((TransitionPhase.DIRECT_MERGE,), manifest.enabled_phases)
        self.assertEqual(
            (
                EffectKind.MERGE_PR,
                EffectKind.MERGE_PR,
                EffectKind.REFRESH_TRUNK,
                EffectKind.SYNC_STACK,
            ),
            tuple(effect.kind for effect in manifest.effects),
        )

    def test_merge_prefix_must_start_at_the_bottom_open_pull_request(self) -> None:
        phases = frozenset({TransitionPhase.DIRECT_MERGE, TransitionPhase.SYNC})

        with self.assertRaisesRegex(ManifestError, "ordered bottom prefix"):
            preview_merge(
                repository="shaug/compris",
                remote="origin",
                pull_requests=self.pull_requests,
                native_stack=self.stack,
                prefix_numbers=(43,),
                merge_mode=MergeMode.DIRECT,
                merge_method="merge",
                trunk_tree_before=SHA_A,
                trunk_tree_after=SHA_B,
                authority=self._authority(
                    StackOperation.MERGE,
                    phases,
                    frozenset({EffectKind.MERGE_PR, EffectKind.SYNC_STACK}),
                    merge_method="merge",
                ),
                evidence=("merge snapshot",),
            )

    def test_recovery_fences_trunk_refresh_rebase_push_pr_and_sync(self) -> None:
        phases = frozenset(
            {
                TransitionPhase.TRUNK_REFRESH,
                TransitionPhase.REBASE_NO_TRUNK,
                TransitionPhase.PUSH,
                TransitionPhase.SYNC,
            }
        )
        manifest = preview_recovery(
            repository="shaug/compris",
            remote="origin",
            refs=self.refs,
            pull_requests=self.pull_requests,
            native_stack=self.stack,
            authority=self._authority(
                StackOperation.RECOVER,
                phases,
                frozenset(
                    {
                        EffectKind.REFRESH_TRUNK,
                        EffectKind.REBASE_BRANCH,
                        EffectKind.PUSH_REF,
                        EffectKind.UPDATE_PR,
                        EffectKind.SYNC_STACK,
                    }
                ),
            ),
            evidence=("recovery snapshot",),
        )

        self.assertEqual(EffectKind.REFRESH_TRUNK, manifest.effects[0].kind)
        self.assertEqual(
            required_capabilities(
                StackOperation.RECOVER,
                phases=manifest.enabled_phases,
                merge_mode=None,
            ),
            frozenset(
                {
                    StackCapability.PHASED_TRUNK_REFRESH,
                    StackCapability.LOCAL_REBASE_NO_TRUNK,
                    StackCapability.FENCED_PUSH,
                    StackCapability.FENCED_SYNC,
                }
            ),
        )

    def test_direct_and_queue_merge_have_distinct_capability_fences(self) -> None:
        direct = required_capabilities(
            StackOperation.MERGE,
            phases=(TransitionPhase.DIRECT_MERGE,),
            merge_mode=MergeMode.DIRECT,
        )
        queued = required_capabilities(
            StackOperation.MERGE,
            phases=(TransitionPhase.QUEUE_MERGE,),
            merge_mode=MergeMode.QUEUE,
        )

        self.assertEqual(frozenset({StackCapability.FENCED_MERGE}), direct)
        self.assertEqual(
            frozenset(
                {
                    StackCapability.FENCED_MERGE,
                    StackCapability.DURABLE_QUEUE_FENCE,
                }
            ),
            queued,
        )

    def test_execution_rereads_the_complete_manifest_before_mutation(self) -> None:
        manifest = publish_manifest()
        stale_stack = replace(
            manifest,
            expected_native_stack=replace(
                manifest.expected_native_stack,
                layers=tuple(reversed(manifest.expected_native_stack.layers)),
            ),
        )
        profile = replace(
            reviewed_preview_profile("14fc42ed9b6c376a53b2f999f138d3bd26dac546"),
            capabilities=required_capabilities(
                manifest.operation,
                phases=manifest.enabled_phases,
                merge_mode=manifest.merge_mode,
            ),
        )
        calls: list[MutationManifest] = []

        result = execute_transition(
            manifest,
            profile=profile,
            reread=lambda: stale_stack,
            executor=lambda approved: calls.append(approved),
            readback=lambda: TransitionObservation.from_manifest_before(manifest),
        )

        self.assertEqual(TransitionState.BLOCKED, result.state)
        self.assertIn("manifest changed during pre-execution reread", result.blocker)
        self.assertEqual([], calls)


class ReadbackClassificationTests(unittest.TestCase):
    def _manifest(self, *effects: MutationEffect) -> MutationManifest:
        return MutationManifest(
            operation=StackOperation.RECOVER,
            repository="shaug/compris",
            remote="origin",
            identities=("stack-9",),
            expected_refs=(),
            expected_pull_requests=(),
            expected_native_stack=ExpectedNativeStack(
                identity="stack-9",
                registered=True,
                trunk="main",
                trunk_head=SHA_A,
                layers=(
                    ExpectedNativeLayer(
                        branch="feature-1",
                        head=SHA_A,
                        base=SHA_A,
                        merged=False,
                        queued=False,
                        needs_rebase=False,
                        pull_request=None,
                        pull_request_state=None,
                    ),
                ),
            ),
            enabled_phases=(TransitionPhase.PUSH,),
            merge_mode=None,
            merge_method=None,
            effects=effects,
            evidence=("snapshot",),
            authority=AuthorityGrant(
                operation=StackOperation.RECOVER,
                repository="shaug/compris",
                remote="origin",
                identities=("stack-9",),
                branches=("feature-1",),
                phases=frozenset({TransitionPhase.PUSH}),
                effect_kinds=frozenset(effect.kind for effect in effects),
            ),
        )

    def test_partial_push_requires_a_fresh_manifest(self) -> None:
        manifest = self._manifest(
            MutationEffect(EffectKind.PUSH_REF, "ref:feature-1", "sha", SHA_A, SHA_C),
            MutationEffect(EffectKind.PUSH_REF, "ref:feature-2", "sha", SHA_B, SHA_D),
        )

        result = classify_readback(
            manifest,
            TransitionObservation(
                values=(("ref:feature-1:sha", SHA_C), ("ref:feature-2:sha", SHA_B))
            ),
        )

        self.assertEqual(TransitionState.PARTIAL, result.state)
        self.assertEqual(
            (
                TargetDisposition.CHANGED_AS_EXPECTED,
                TargetDisposition.UNCHANGED,
            ),
            tuple(item.disposition for item in result.targets),
        )
        self.assertTrue(result.fresh_manifest_required)

    def test_live_observation_projects_synced_branch_head_from_fresh_ref(self) -> None:
        approved = self._manifest(
            MutationEffect(
                EffectKind.SYNC_STACK,
                "stack:stack-9:feature-1",
                "head",
                SHA_A,
                SHA_C,
            )
        )
        current = replace(
            approved,
            expected_refs=(ExpectedRef("refs/heads/feature-1", SHA_C, SHA_C),),
        )

        observation = observation_from_manifest(approved, current)

        self.assertEqual((("stack:stack-9:feature-1:head", SHA_C),), observation.values)

    def test_complete_and_no_op_results_remain_distinct(self) -> None:
        changing = self._manifest(
            MutationEffect(EffectKind.PUSH_REF, "ref:feature-1", "sha", SHA_A, SHA_C)
        )
        no_op = self._manifest(
            MutationEffect(EffectKind.PUSH_REF, "ref:feature-1", "sha", SHA_A, SHA_A)
        )

        completed = classify_readback(
            changing,
            TransitionObservation(values=(("ref:feature-1:sha", SHA_C),)),
        )
        unchanged = classify_readback(
            no_op,
            TransitionObservation(values=(("ref:feature-1:sha", SHA_A),)),
        )

        self.assertEqual(TransitionState.COMPLETED, completed.state)
        self.assertEqual(TransitionState.UNCHANGED, unchanged.state)
        self.assertFalse(completed.fresh_manifest_required)
        self.assertFalse(unchanged.fresh_manifest_required)

    def test_newly_created_ref_is_changed_unexpectedly(self) -> None:
        manifest = self._manifest(
            MutationEffect(EffectKind.PUSH_REF, "ref:feature-2", "sha", ZERO_SHA, SHA_D)
        )

        result = classify_readback(
            manifest,
            TransitionObservation(values=(("ref:feature-2:sha", SHA_C),)),
        )

        self.assertEqual(TransitionState.DIVERGED, result.state)
        self.assertEqual(
            TargetDisposition.CHANGED_UNEXPECTEDLY, result.targets[0].disposition
        )
        self.assertTrue(result.fresh_manifest_required)

    def test_newly_created_pull_request_is_classified_after_submit(self) -> None:
        created = (
            51,
            "feature-1",
            SHA_C,
            "main",
            "OPEN",
            False,
            False,
            False,
            "Layer 1",
            "Layer 1 body",
        )
        manifest = self._manifest(
            MutationEffect(
                EffectKind.CREATE_PR,
                "pr:feature-1",
                "record",
                None,
                created,
            )
        )

        result = classify_readback(
            manifest,
            TransitionObservation(values=(("pr:feature-1:record", created),)),
        )

        self.assertEqual(TransitionState.COMPLETED, result.state)
        self.assertEqual(
            TargetDisposition.CHANGED_AS_EXPECTED,
            result.targets[0].disposition,
        )

    def test_pr_state_drift_and_stack_reorder_are_each_classified(self) -> None:
        manifest = self._manifest(
            MutationEffect(EffectKind.UPDATE_PR, "pr:41", "base", "main", "feature-1"),
            MutationEffect(
                EffectKind.REGISTER_STACK,
                "stack:stack-9",
                "order",
                ("feature-1", "feature-2"),
                ("feature-1", "feature-2"),
            ),
        )

        result = classify_readback(
            manifest,
            TransitionObservation(
                values=(
                    ("pr:41:base", "release"),
                    ("stack:stack-9:order", ("feature-2", "feature-1")),
                )
            ),
        )

        self.assertEqual(TransitionState.DIVERGED, result.state)
        self.assertEqual(
            (TargetDisposition.CHANGED_UNEXPECTEDLY,) * 2,
            tuple(item.disposition for item in result.targets),
        )

    def test_pr_draft_and_auto_merge_drift_are_each_classified(self) -> None:
        manifest = self._manifest(
            MutationEffect(EffectKind.UPDATE_PR, "pr:41", "draft", False, False),
            MutationEffect(
                EffectKind.DISABLE_AUTO_MERGE,
                "pr:41",
                "auto_merge",
                True,
                False,
            ),
        )

        result = classify_readback(
            manifest,
            TransitionObservation(
                values=(("pr:41:draft", True), ("pr:41:auto_merge", None))
            ),
        )

        self.assertEqual(TransitionState.DIVERGED, result.state)
        self.assertEqual(
            (TargetDisposition.CHANGED_UNEXPECTEDLY,) * 2,
            tuple(item.disposition for item in result.targets),
        )

    def test_partial_direct_merge_is_distinct_from_queue_admission(self) -> None:
        direct = self._manifest(
            MutationEffect(EffectKind.MERGE_PR, "pr:41", "state", "OPEN", "MERGED"),
            MutationEffect(EffectKind.MERGE_PR, "pr:42", "state", "OPEN", "MERGED"),
        )
        queued = self._manifest(
            MutationEffect(EffectKind.QUEUE_PR, "pr:41", "queued", False, True),
            MutationEffect(EffectKind.MERGE_PR, "pr:41", "state", "OPEN", "MERGED"),
        )

        direct_result = classify_readback(
            direct,
            TransitionObservation(
                values=(("pr:41:state", "MERGED"), ("pr:42:state", "OPEN"))
            ),
        )
        queue_result = classify_readback(
            queued,
            TransitionObservation(
                values=(("pr:41:queued", True), ("pr:41:state", "OPEN"))
            ),
        )

        self.assertEqual(TransitionState.PARTIAL, direct_result.state)
        self.assertEqual(TransitionState.PARTIAL, queue_result.state)
        self.assertEqual(
            TargetDisposition.CHANGED_AS_EXPECTED,
            queue_result.targets[0].disposition,
        )
        self.assertEqual(
            TargetDisposition.UNCHANGED, queue_result.targets[1].disposition
        )


if __name__ == "__main__":
    unittest.main()
