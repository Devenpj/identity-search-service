-- Seed one completed OSINT job for dashboard display testing.
-- Safe to rerun: it updates the same JOBDUMMY01 row.

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
    'JOBDUMMY01',
    'COMPLETED',
    '[
        {"key": "username", "value": "ad018jan"},
        {"key": "email", "value": "devendraprajapt42@gmail.com"},
        {"key": "phone", "value": "7742736948"}
    ]'::jsonb,
    '{"job_id": "JOBDUMMY01", "status": "processing", "message": "Dummy OSINT job seeded locally."}'::jsonb,
    '{
        "profile_url": "https://www.instagram.com/ad018jan/",
        "inputs_processed": ["ad018jan", "devendraprajapt42@gmail.com", "7742736948"],
        "username_results": [
            {
                "target": "ad018jan",
                "platform": "Hackerearth",
                "url": "https://hackerearth.com/@ad018jan",
                "status": "Verified Profile Account Located"
            },
            {
                "target": "ad018jan",
                "platform": "GitHub",
                "url": "https://github.com/ad018jan",
                "status": "Possible Username Match"
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
                    "bio": "Cyber security learner and open-source contributor.",
                    "avatar_url": "https://example.com/avatar/ad018jan.jpg",
                    "followers": 1240,
                    "following": 388,
                    "top_posts": [
                        {
                            "caption": "Security research notes",
                            "url": "https://www.instagram.com/p/dummy-post-1/"
                        },
                        {
                            "caption": "Conference day",
                            "url": "https://www.instagram.com/p/dummy-post-2/"
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
                    "location": "India",
                    "confidence": "medium",
                    "public_posts": [
                        {
                            "title": "Public profile activity",
                            "url": "https://www.facebook.com/ad018jan/posts/dummy"
                        }
                    ]
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
                        "details": "Current Active Carrier: Bharti Airtel Ltd\nRegistration Country Base: India\nRouting Status: Live Switch Active"
                    },
                    {
                        "platform": "Native Phonenumbers Core",
                        "details": "Structural Format: Mobile Number\nRegion/Circle Assignment: India\nCountry Validity Index: Valid E.164 Route"
                    }
                ]
            }
        ],
        "email_results": [
            {
                "status": "failed",
                "target": "devendraprajapt42@gmail.com",
                "input_type": "email",
                "message": "Dummy validation gate returned limited data.",
                "matches": [
                    {
                        "platform": "Gmail Target Verification Gate",
                        "category": "infrastructure_telemetry",
                        "status": "Limited Verification",
                        "details": "Dummy payload: email syntax valid, deeper provider verification skipped."
                    }
                ],
                "metrics": {
                    "live_gateways_found": 1,
                    "total_indicators_mapped": 3,
                    "username_variations_found": 4
                }
            }
        ],
        "all_matches": [
            {
                "platform": "Pinterest",
                "url": "https://www.pinterest.com/ad018jan/",
                "enriched_data": {
                    "bio": "Dummy enriched profile for dashboard testing.",
                    "avatar_url": "https://example.com/avatar/pinterest-ad018jan.jpg",
                    "local_avatar_path": "avatars/ad018jan.jpg"
                }
            }
        ],
        "risk_notes": {
            "summary": "Dummy OSINT payload used for dashboard rendering tests.",
            "confidence": "test-only",
            "source_count": 6
        }
    }'::jsonb,
    '{
        "job_id": "JOBDUMMY01",
        "status": "completed",
        "message": "Dummy completed OSINT payload."
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
