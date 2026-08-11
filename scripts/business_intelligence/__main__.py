"""Operator CLI: ``python -m business_intelligence <command>``.

Commands:
  rebuild            Run the full bootstrap pipeline
  status             Print current profile + critic verdict + counts
  compile-conversion Print the conversion context (optional segment/offering)
  compile-creative   Print the creative context (optional territory/segment)
  compile-orchestrator Print the orchestrator context
"""

from __future__ import annotations

import argparse
import json
import sys

from . import api


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="business_intelligence")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_rebuild = sub.add_parser("rebuild")
    p_rebuild.add_argument("--reset-evidence", action="store_true")

    sub.add_parser("status")

    p_conv = sub.add_parser("compile-conversion")
    p_conv.add_argument("--segment", default="")
    p_conv.add_argument("--offering", default="")

    p_creative = sub.add_parser("compile-creative")
    p_creative.add_argument("--territory", default="")
    p_creative.add_argument("--segment", default="")

    sub.add_parser("compile-orchestrator")

    args = parser.parse_args(argv)

    if args.cmd == "rebuild":
        out = api.rebuild_profile(reset_evidence=args.reset_evidence)
    elif args.cmd == "status":
        prof = api.get_business_profile()
        verdict = api.critic_review()
        out = {
            "profile_version": prof.get("profile_version"),
            "generated_at": prof.get("generated_at"),
            "identity": prof.get("identity", {}),
            "offerings": len(prof.get("offerings", [])),
            "audience_segments": len(prof.get("audience_segments", [])),
            "content_territories": len(prof.get("content_territories", [])),
            "critic": verdict,
        }
    elif args.cmd == "compile-conversion":
        out = api.compile_conversion_context(segment_id=args.segment, offering_id=args.offering)
    elif args.cmd == "compile-creative":
        out = api.compile_creative_context(territory_id=args.territory, segment_id=args.segment)
    elif args.cmd == "compile-orchestrator":
        out = api.compile_orchestrator_context()
    else:
        parser.print_help()
        return 2

    json.dump(out, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
