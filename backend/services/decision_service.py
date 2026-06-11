"""Decision builder for the final verification status shown to users."""


class DecisionService:
    """Convert database, face, and risk results into a user-facing decision."""

    def build_decision(
        self,
        database_match,
        face_result=None,
        risk_assessment=None
    ):
        """Return VERIFIED, MANUAL REVIEW, or NOT VERIFIED for one case.

        Risk scoring is the primary decision source when present. Older flows
        can still call this with only database and face results, so the fallback
        logic remains available for simpler verification paths.
        """

        if risk_assessment:

            risk_decision = risk_assessment.get("decision")
            risk_score = risk_assessment.get("risk_score")
            risk_level = risk_assessment.get("risk_level")

            if risk_decision == "APPROVED":

                return {
                    "status": "VERIFIED",
                    "message": f"Identity approved with risk score {risk_score}/100 ({risk_level} risk)",
                    "risk_assessment": risk_assessment
                }

            if risk_decision == "MANUAL REVIEW":

                return {
                    "status": "MANUAL REVIEW",
                    "message": f"Identity needs manual review with risk score {risk_score}/100 ({risk_level} risk)",
                    "risk_assessment": risk_assessment
                }

            return {
                "status": "NOT VERIFIED",
                "message": f"Identity rejected with risk score {risk_score}/100 ({risk_level} risk)",
                "risk_assessment": risk_assessment
            }

        if not database_match:

            return {
                "status": "NOT VERIFIED",
                "message": "No matching user found in database"
            }

        if face_result and face_result.get("matched"):

            return {
                "status": "VERIFIED",
                "message": "User exists in database and face matched"
            }

        return {
            "status": "MANUAL REVIEW",
            "message": "User exists in database, but face did not match confidently"
        }
