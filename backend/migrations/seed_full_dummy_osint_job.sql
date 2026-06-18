-- Seed a full completed OSINT job for dashboard display testing.
-- Safe to rerun: it updates the same JOBDUMMYFULL01 row.

INSERT INTO osint_jobs (
    job_id,
    status,
    targets,
    provider_response,
    result,
    result_payload,
    error_message,
    created_at,
    submitted_at,
    completed_at,
    updated_at
)
VALUES (
    'JOBDUMMYFULL01',
    'COMPLETED',
    '[
        {"key": "username", "value": "ad018jan"},
        {"key": "full_name", "value": "Aditya Jan"},
        {"key": "email", "value": "aditya.jan@example.com"},
        {"key": "phone", "value": "7742736948"}
    ]'::jsonb,
    '{
        "job_id": "JOBDUMMYFULL01",
        "status": "processing",
        "message": "Full dummy OSINT test job accepted."
    }'::jsonb,
    '{
        "profile_url": "https://www.instagram.com/ad018jan/",
        "inputs_processed": [
            "ad018jan",
            "Aditya Jan",
            "aditya.jan@example.com",
            "7742736948"
        ],
        "username_results": [
            {
                "target": "ad018jan",
                "platform": "GitHub",
                "url": "https://github.com/ad018jan",
                "status": "Possible Username Match",
                "details": "Public username profile located with matching handle and technical repositories."
            },
            {
                "target": "ad018jan",
                "platform": "Hackerearth",
                "url": "https://hackerearth.com/@ad018jan",
                "status": "Verified Profile Account Located",
                "details": "Competitive programming profile found with visible username and public activity."
            }
        ],
        "instagram_results": [
            {
                "target_username": "ad018jan",
                "platform": "Instagram",
                "status": "Target Profile Analysis",
                "profile_url": "https://www.instagram.com/ad018jan/",
                "extracted_data": {
                    "profile_url": "https://www.instagram.com/ad018jan/",
                    "display_name": "Aditya Jan",
                    "bio": "Security researcher, student, and open-source learner.",
                    "avatar_url": "https://example.com/assets/ad018jan-instagram-avatar.jpg",
                    "followers": 1240,
                    "following": 388,
                    "account_type": "public",
                    "top_posts": [
                        {
                            "caption": "Security research notes from a weekend lab.",
                            "url": "https://www.instagram.com/p/dummy-security-lab/"
                        },
                        {
                            "caption": "Open-source contribution milestone.",
                            "url": "https://www.instagram.com/p/dummy-open-source/"
                        }
                    ]
                }
            }
        ],
        "facebook_results": [
            {
                "target": "ad018jan",
                "platform": "Facebook",
                "status": "Possible Profile Located",
                "profile_url": "https://www.facebook.com/ad018jan",
                "details": {
                    "display_name": "Aditya Jan",
                    "location": "Jaipur, Rajasthan",
                    "confidence": "medium",
                    "public_profile": true,
                    "public_posts": [
                        {
                            "title": "Cyber awareness workshop post",
                            "url": "https://www.facebook.com/ad018jan/posts/dummy-cyber-awareness"
                        }
                    ]
                }
            }
        ],
        "linkedin_results": [
            {
                "target": "Aditya Jan",
                "platform": "LinkedIn",
                "status": "Professional Profile Candidate",
                "profile_url": "https://www.linkedin.com/in/aditya-jan-dummy",
                "details": {
                    "headline": "Cyber Security Analyst Intern",
                    "company": "Example Security Labs",
                    "location": "India",
                    "confidence": "medium"
                }
            }
        ],
        "all_matches": [
            {
                "platform": "Pinterest",
                "url": "https://www.pinterest.com/ad018jan/",
                "enriched_data": {
                    "bio": "Cyber security and technology boards.",
                    "avatar_url": "https://example.com/assets/ad018jan-pinterest-avatar.jpg",
                    "local_avatar_path": "avatars/ad018jan-pinterest.jpg",
                    "confidence": "medium"
                }
            },
            {
                "platform": "AboutMe",
                "url": "https://about.me/ad018jan",
                "enriched_data": {
                    "bio": "Student profile with matching username, email pattern, and technology interests.",
                    "avatar_url": "https://example.com/assets/ad018jan-aboutme-avatar.jpg",
                    "local_avatar_path": "avatars/ad018jan-aboutme.jpg",
                    "confidence": "high"
                }
            }
        ],
        "phone_results": [
            {
                "status": "success",
                "target": "+917742736948",
                "input_type": "phone",
                "matches": [
                    {
                        "platform": "Live Network State: Bharti Airtel Ltd",
                        "status": "Verified Route",
                        "category": "telecom",
                        "details": "Current Active Carrier: Bharti Airtel Ltd\nRegistration Country Base: India\nRouting Status: Live Switch Active\nLine Type: Mobile"
                    },
                    {
                        "platform": "Native Phonenumbers Core",
                        "status": "Valid Number Format",
                        "category": "phone_format",
                        "details": "Structural Format: Indian Mobile Number\nRegion/Circle Assignment: India\nCountry Validity Index: Valid E.164 Route"
                    }
                ]
            }
        ],
        "email_results": [
            {
                "status": "success",
                "target": "aditya.jan@example.com",
                "input_type": "email",
                "message": "Email syntax and domain telemetry checked successfully.",
                "matches": [
                    {
                        "platform": "Email Syntax Gate",
                        "category": "email_validation",
                        "status": "Valid Format",
                        "details": "Email format passed strict validation checks.\nMailbox verification skipped for dummy data."
                    },
                    {
                        "platform": "Domain Intelligence",
                        "category": "domain_telemetry",
                        "status": "Domain Reachable",
                        "details": "Domain has valid DNS records in dummy telemetry.\nNo breach indicators included in this test payload."
                    }
                ],
                "metrics": {
                    "live_gateways_found": 2,
                    "total_indicators_mapped": 6,
                    "username_variations_found": 4
                }
            }
        ]
    }'::jsonb,
    '{
        "job_id": "JOBDUMMYFULL01",
        "status": "completed",
        "message": "Full dummy OSINT payload loaded for dashboard testing."
    }'::jsonb,
    NULL,
    CURRENT_TIMESTAMP,
    CURRENT_TIMESTAMP,
    CURRENT_TIMESTAMP,
    CURRENT_TIMESTAMP
)
ON CONFLICT (job_id)
DO UPDATE SET
    status = EXCLUDED.status,
    targets = EXCLUDED.targets,
    provider_response = EXCLUDED.provider_response,
    result = EXCLUDED.result,
    result_payload = EXCLUDED.result_payload,
    error_message = NULL,
    submitted_at = EXCLUDED.submitted_at,
    completed_at = EXCLUDED.completed_at,
    updated_at = CURRENT_TIMESTAMP;
