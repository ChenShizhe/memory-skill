"""Snapshot of `route_card` as of pre-2026-05-01-widening (commit fb78d5c).

This fixture preserves the routing logic that produced the current
`memories/catalog-shards/*` distribution. It is used by the differential
test (`TestDifferentialRouteCard`) to verify that the 2026-05-01 ladder
widening only changes routing for whitelisted slugs.

Do not edit. When the next routing-rule PR lands, this file should be
regenerated from the *then*-current `bootstrap.py:route_card` body.
"""

from __future__ import annotations


CORE_IDENTITY_PATHS_OLD = {
    "memories/AGENTS.md",
    "memories/SOUL.md",
    "memories/IDENTITY.md",
    "memories/USER.md",
}


GRADUATED_PROJECTS_OLD: set[str] = {
    "coordination",
    "git-integration",
    "learning-by-doing",
    "memory-manager-v0",
    "paper-reader-improvement",
    "research-meeting",
    "skill-publication",
}


def _as_list(value) -> list[str]:
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    if isinstance(value, str):
        v = value.strip()
        if v.startswith("[") and v.endswith("]"):
            inner = v[1:-1].strip()
            if not inner:
                return []
            return [x.strip() for x in inner.split(",") if x.strip()]
        return [v] if v else []
    return []


def route_card_old(frontmatter: dict) -> str:
    """Snapshot of the pre-2026-05-01 routing ladder. First-match-wins."""
    path = str(frontmatter.get("path", "")).strip()
    type_ = str(frontmatter.get("type", "")).strip()
    slug = str(frontmatter.get("slug", "")).strip()
    projects = _as_list(frontmatter.get("projects"))
    topics = _as_list(frontmatter.get("topics"))
    topics_l = {t.lower() for t in topics}

    # 1. Core identity paths
    if path in CORE_IDENTITY_PATHS_OLD:
        return "core-identity.md"
    # 2. workflow_template
    if type_ == "workflow_template":
        return "workflow-templates.md"
    # 3. role_profile
    if type_ == "role_profile":
        return "roles.md"
    # 4. hub
    if type_ == "hub":
        return "hubs.md"
    # 5. sole graduated project
    if len(projects) == 1 and projects[0] in GRADUATED_PROJECTS_OLD:
        return f"project-{projects[0]}.md"
    # 6. sole below-threshold project
    if len(projects) == 1:
        return "project-continuity.md"
    # 7. paper-reading
    if (slug.startswith("paper-reader-") or slug.startswith("paper-discovery-")
            or slug.startswith("paper-review-")):
        return "paper-reading.md"
    if "paper-reading" in topics_l or "paper-reader" in topics_l:
        return "paper-reading.md"
    # 8. memory-system
    if (slug.startswith("memory-") or slug.startswith("catalog-")
            or slug.startswith("experience-logger-")
            or slug.startswith("knowledge-maester-")):
        return "memory-system.md"
    if "memory-ingestion" in topics_l or "retrieval" in topics_l or "catalog" in topics_l:
        return "memory-system.md"
    # 9. market-ops
    if slug.startswith("market-") or slug.startswith("portfolio-"):
        return "market-ops.md"
    if "market-watcher" in topics_l or "portfolio" in topics_l or "ticker" in topics_l:
        return "market-ops.md"
    # 10. tooling-ops
    if "credential" in slug or "broker" in slug or "git-" in slug:
        return "tooling-ops.md"
    if ("credential-broker" in topics_l or "env-vars" in topics_l
            or "secret-handling" in topics_l or "git" in topics_l):
        return "tooling-ops.md"
    # 11. session-ops
    if "research-meeting-" in slug or "session-" in slug:
        return "session-ops.md"
    if "research-meeting" in topics_l or "session-handoff" in topics_l:
        return "session-ops.md"
    # 12. skill-ops
    if slug.startswith("ralph-") or slug.startswith("skill-"):
        return "skill-ops.md"
    if ("skill-design" in topics_l or "skill-testing" in topics_l
            or "skill-onboarding" in topics_l or "strangler-fig" in topics_l):
        return "skill-ops.md"
    # 13. agent-ops
    if ("agent-ops" in topics_l or "preflight" in topics_l
            or "paper-trail" in topics_l or "safety" in topics_l):
        return "agent-ops.md"
    # 14. writing-style
    writing_topics = {"writing", "manuscript", "review", "academic-writing"}
    has_writing_topic = bool(topics_l & writing_topics)
    if has_writing_topic:
        return "writing-style.md"
    if type_ in {"user_preference", "user-preference"} and has_writing_topic:
        return "writing-style.md"
    # 15. misc
    return "misc.md"
