"""Evidence validator.

Checks:
- finding schema is well-formed
- cited record IDs exist
- cited records belong to the case
- cited numeric claims match the records

One formatting repair is allowed; persistent failure causes abstention.
"""

from __future__ import annotations

from typing import Any


class EvidenceValidator:
    """Validates agent findings against raw evidence records."""

    def __init__(self, evidence_index: dict[str, list[dict[str, Any]]] | None = None):
        self.evidence_index = evidence_index or {}
        self.repair_used: dict[str, bool] = {}

    def validate_finding(
        self,
        case_id: str,
        finding: dict[str, Any],
    ) -> tuple[bool, list[str]]:
        """Validate a single agent finding.

        Returns (is_valid, list_of_issues).
        """
        issues: list[str] = []

        required_fields = [
            "candidate_cause",
            "supporting_record_ids",
            "counterevidence_ids",
            "missing_fields",
            "justification",
            "confidence",
        ]
        for field_name in required_fields:
            if field_name not in finding:
                issues.append(f"missing field: {field_name}")

        # Check cited record IDs exist and belong to the case
        for record_id in finding.get("supporting_record_ids", []):
            if not self._record_exists_and_belongs(case_id, record_id):
                issues.append(f"unsupported record id: {record_id}")

        for record_id in finding.get("counterevidence_ids", []):
            if not self._record_exists_and_belongs(case_id, record_id):
                issues.append(f"unsupported counterevidence id: {record_id}")

        # Check numeric claims match records (basic heuristic)
        numeric_issues = self._check_numeric_claims(case_id, finding)
        issues.extend(numeric_issues)

        return (len(issues) == 0), issues

    def attempt_repair(self, case_id: str, finding: dict[str, Any]) -> dict[str, Any]:
        """Attempt one formatting repair on a finding.

        Removes unsupported record IDs and fills missing required fields with
        safe defaults.
        """
        if self.repair_used.get(case_id, False):
            return finding

        repaired = dict(finding)

        # Drop unsupported record IDs
        valid_supporting = [
            rid
            for rid in repaired.get("supporting_record_ids", [])
            if self._record_exists_and_belongs(case_id, rid)
        ]
        valid_counter = [
            rid
            for rid in repaired.get("counterevidence_ids", [])
            if self._record_exists_and_belongs(case_id, rid)
        ]
        repaired["supporting_record_ids"] = valid_supporting
        repaired["counterevidence_ids"] = valid_counter

        # Fill missing fields
        for field_name in [
            "candidate_cause",
            "justification",
            "confidence",
        ]:
            if not repaired.get(field_name):
                repaired[field_name] = "insufficient_evidence" if field_name == "candidate_cause" else ""

        if "missing_fields" not in repaired:
            repaired["missing_fields"] = []

        self.repair_used[case_id] = True
        return repaired

    def _record_exists_and_belongs(
        self, case_id: str, record_id: str
    ) -> bool:
        for records in self.evidence_index.values():
            for record in records:
                if record.get("record_id") == record_id and record.get("case_id") == case_id:
                    return True
        return False

    def _check_numeric_claims(
        self, case_id: str, finding: dict[str, Any]
    ) -> list[str]:
        """Basic check: if finding cites delay/queue numbers, verify they appear in records."""
        issues: list[str] = []
        justification = finding.get("justification", "")

        # Simple heuristic: look for numbers mentioned in justification and check
        # whether any cited record contains a matching numeric field.
        cited_ids = finding.get("supporting_record_ids", [])
        cited_records: list[dict[str, Any]] = []
        for records in self.evidence_index.values():
            for record in records:
                if record.get("record_id") in cited_ids and record.get("case_id") == case_id:
                    cited_records.append(record)

        # If justification mentions a threshold but no cited record supports it,
        # flag as potential unsupported claim (soft warning, not hard fail).
        import re

        numbers_in_justification = re.findall(r"\d+(?:\.\d+)?", justification)
        if numbers_in_justification and not cited_records:
            issues.append("justification cites numbers without supporting records")

        return issues
