"""Streamlit dashboard for identity search, document validation, and admin work.

This file is the operator-facing UI. It renders tabs, sends form data to the
FastAPI backend, and turns backend JSON responses into readable tables, status
panels, evidence images, score cards, and review workflows.
"""

import json
import html
import os
import re
import uuid
import base64

import requests
import streamlit as st
from PIL import Image
from PIL import UnidentifiedImageError


API_URL = "http://127.0.0.1:8000/search-identity"
ADVANCED_SEARCH_URL = "http://127.0.0.1:8000/search-identity-advanced"
VALIDATE_ID_URL = "http://127.0.0.1:8000/validate-id"
DOCUMENT_VALIDATION_JOBS_URL = "http://127.0.0.1:8000/api/v1/jobs/document-validation"
EXTRACT_DOCUMENT_FIELDS_URL = "http://127.0.0.1:8000/extract-document-fields"
FACE_SEARCH_URL = "http://127.0.0.1:8000/search-by-face"
FACE_SEARCH_JOBS_URL = "http://127.0.0.1:8000/api/v1/jobs/face-search"
MANUAL_REVIEW_URL = "http://127.0.0.1:8000/manual-review-cases"
ADMIN_IDENTITIES_URL = "http://127.0.0.1:8000/admin/identities"
OSINT_JOBS_URL = "http://127.0.0.1:8000/api/v1/osint/jobs"
OSINT_SUBMIT_URL = "http://127.0.0.1:8000/api/v1/osint/jobs"
OSINT_AVATAR_VERIFY_URL = "http://127.0.0.1:8000/api/v1/osint/jobs"
NEWS_TOP_CLUSTERS_URL = "http://127.0.0.1:8000/api/v1/news/clusters/top"
NEWS_SEARCH_URL = "http://127.0.0.1:8000/api/v1/news/search"
NEWS_TOPICS_URL = "http://127.0.0.1:8000/api/v1/news/topics"
NEWS_CLUSTER_URL = "http://127.0.0.1:8000/api/v1/news/clusters"
NEWS_SYNC_STATUS_URL = "http://127.0.0.1:8000/api/v1/news/sync-status/latest"
DRISHTI_OVERVIEW_URL = "http://127.0.0.1:8000/api/v1/drishti/overview"
DRISHTI_REFRESH_URL = "http://127.0.0.1:8000/api/v1/drishti/refresh"
DRISHTI_SEARCH_URL = "http://127.0.0.1:8000/api/v1/drishti/search"
DRISHTI_CONTENT_URL = "http://127.0.0.1:8000/api/v1/drishti/content/generate"


st.set_page_config(
    page_title="Identity Verification Command Center",
    layout="wide",
    initial_sidebar_state="expanded"
)


st.markdown(
    """
    <style>
        :root {
            --surface: #ffffff;
            --surface-soft: #f6f8fb;
            --ink: #172033;
            --muted: #667085;
            --line: #d9e0ea;
            --brand: #0f5e73;
            --brand-soft: #e8f5f7;
            --success: #087443;
            --success-soft: #e7f8ef;
            --warning: #9a5b00;
            --warning-soft: #fff4df;
            --danger: #b42318;
            --danger-soft: #fff0ee;
        }

        .stApp,
        div[data-testid="stAppViewContainer"],
        div[data-testid="stAppViewContainer"] > .main,
        div[data-testid="stToolbar"],
        div[data-testid="stDecoration"],
        div[data-testid="stStatusWidget"],
        iframe {
            background: #f4f7fb !important;
            color: #172033 !important;
        }

        header[data-testid="stHeader"] {
            background: rgba(244, 247, 251, 0.96) !important;
        }

        section[data-testid="stSidebar"],
        section[data-testid="stSidebar"] > div,
        div[data-testid="stSidebar"],
        div[data-testid="stSidebar"] > div,
        div[data-testid="stSidebarContent"],
        div[data-testid="stSidebarUserContent"] {
            background: linear-gradient(180deg, #ffffff 0%, #f3f8fb 100%) !important;
            color: #172033 !important;
        }

        section[data-testid="stSidebar"] > div,
        div[data-testid="stSidebar"] > div {
            border-right: 1px solid var(--line) !important;
            padding-top: 1.2rem !important;
        }

        section[data-testid="stSidebar"] *,
        div[data-testid="stSidebar"] * {
            color: #172033 !important;
        }

        section[data-testid="stSidebar"] .stRadio > label,
        div[data-testid="stSidebar"] .stRadio > label {
            color: #667085 !important;
            font-size: 12px !important;
            font-weight: 850 !important;
            text-transform: uppercase !important;
        }

        section[data-testid="stSidebar"] div[role="radiogroup"] label,
        div[data-testid="stSidebar"] div[role="radiogroup"] label {
            background: #ffffff !important;
            border: 1px solid #d9e0ea !important;
            border-radius: 8px !important;
            padding: 9px 10px !important;
            margin: 5px 0 !important;
            min-height: 42px !important;
            box-shadow: 0 6px 18px rgba(15, 34, 52, 0.04) !important;
        }

        section[data-testid="stSidebar"] div[role="radiogroup"] label:hover,
        div[data-testid="stSidebar"] div[role="radiogroup"] label:hover {
            background: #e8f5f7 !important;
            border-color: #b8dfe6 !important;
        }

        section[data-testid="stSidebar"] div[role="radiogroup"] label *,
        div[data-testid="stSidebar"] div[role="radiogroup"] label * {
            color: #172033 !important;
            font-weight: 750 !important;
        }

        section[data-testid="stSidebar"] button,
        section[data-testid="stSidebar"] button *,
        section[data-testid="stSidebar"] svg,
        div[data-testid="stSidebar"] button,
        div[data-testid="stSidebar"] button *,
        div[data-testid="stSidebar"] svg {
            color: #0f5e73 !important;
            fill: #0f5e73 !important;
        }

        h1, h2, h3, h4, h5, h6,
        p, span, label, small, strong,
        div[data-testid="stCaptionContainer"],
        div[data-testid="stMarkdownContainer"] {
            color: #172033 !important;
        }

        .block-container {
            padding-top: 1.2rem;
            padding-bottom: 2rem;
            max-width: 1320px;
        }

        div[data-testid="stTabs"] button {
            font-weight: 700;
            color: #334155 !important;
        }

        div[data-testid="stTabs"] button[aria-selected="true"] {
            color: #0f5e73 !important;
        }

        div[data-testid="stMetric"] {
            background: var(--surface);
            border: 1px solid var(--line);
            border-radius: 8px;
            padding: 12px 14px;
        }

        div[data-testid="stMetric"] * {
            color: #172033 !important;
        }

        div[data-testid="stMetricLabel"] {
            color: #667085 !important;
        }

        div[data-testid="stMetricValue"] {
            color: #172033 !important;
            font-weight: 800 !important;
        }

        .stTextInput label,
        .stSelectbox label,
        .stFileUploader label {
            color: #172033 !important;
            font-weight: 700 !important;
        }

        .stTextInput input,
        div[data-baseweb="input"],
        div[data-baseweb="input"] > div,
        div[data-testid="stTextInput"] div[data-baseweb="input"],
        div[data-baseweb="select"] > div {
            background: #ffffff !important;
            color: #172033 !important;
            border-color: #c8d2df !important;
            min-height: 46px !important;
        }

        .stTextInput input:focus,
        .stTextInput input:active,
        .stTextInput input:hover,
        .stTextInput input:valid,
        .stTextInput input:invalid,
        input[data-baseweb="input"],
        input[data-baseweb="input"]:focus,
        input[data-baseweb="input"]:active {
            background: #ffffff !important;
            color: #172033 !important;
            caret-color: #172033 !important;
            border-color: #0f5e73 !important;
            box-shadow: none !important;
        }

        .stTextInput input:disabled,
        input[data-baseweb="input"]:disabled,
        div[data-testid="stTextInput"] input:disabled {
            background: #f8fafc !important;
            color: #172033 !important;
            -webkit-text-fill-color: #172033 !important;
            opacity: 1 !important;
            border-color: #c8d2df !important;
            cursor: default !important;
        }

        div[data-testid="stTextInput"] div[data-disabled="true"],
        div[data-baseweb="input"][aria-disabled="true"] {
            background: #f8fafc !important;
            opacity: 1 !important;
        }

        .stTextInput input::selection,
        input[data-baseweb="input"]::selection,
        ::selection {
            background: #b8e4ea !important;
            color: #172033 !important;
        }

        .stTextInput input:-webkit-autofill,
        .stTextInput input:-webkit-autofill:hover,
        .stTextInput input:-webkit-autofill:focus,
        input[data-baseweb="input"]:-webkit-autofill,
        input[data-baseweb="input"]:-webkit-autofill:hover,
        input[data-baseweb="input"]:-webkit-autofill:focus {
            -webkit-box-shadow: 0 0 0 1000px #ffffff inset !important;
            box-shadow: 0 0 0 1000px #ffffff inset !important;
            -webkit-text-fill-color: #172033 !important;
            caret-color: #172033 !important;
            border-color: #0f5e73 !important;
        }

        div[data-baseweb="select"],
        div[data-baseweb="select"] * {
            color: #172033 !important;
        }

        div[data-baseweb="select"] span,
        div[data-baseweb="select"] svg {
            color: #172033 !important;
            fill: #172033 !important;
        }

        div[data-baseweb="popover"],
        div[data-baseweb="popover"] > div,
        div[data-baseweb="tooltip"],
        div[role="tooltip"],
        ul[role="listbox"],
        div[role="listbox"],
        div[data-baseweb="menu"] {
            background: #ffffff !important;
            color: #172033 !important;
            border: 1px solid #c8d2df !important;
            box-shadow: 0 14px 34px rgba(15, 34, 52, 0.18) !important;
        }

        div[data-baseweb="popover"] *,
        div[data-baseweb="tooltip"] *,
        div[role="tooltip"] *,
        ul[role="listbox"] *,
        div[role="listbox"] *,
        div[data-baseweb="menu"] * {
            color: #172033 !important;
        }

        div[role="option"],
        li[role="option"],
        div[data-baseweb="menu"] li,
        div[data-baseweb="menu"] div {
            background: #ffffff !important;
            color: #172033 !important;
        }

        div[role="option"]:hover,
        li[role="option"]:hover,
        div[aria-selected="true"],
        li[aria-selected="true"],
        div[data-baseweb="menu"] li:hover {
            background: #e8f5f7 !important;
            color: #0f5e73 !important;
        }

        .stTextInput input::placeholder {
            color: #8a95a5 !important;
        }

        div[data-testid="stFileUploader"],
        div[data-testid="stFileUploader"] section,
        div[data-testid="stFileUploader"] div,
        section[data-testid="stFileUploaderDropzone"],
        div[data-testid="stFileUploaderDropzone"] {
            background: #ffffff !important;
            color: #172033 !important;
        }

        section[data-testid="stFileUploaderDropzone"],
        div[data-testid="stFileUploaderDropzone"] {
            border: 1px dashed #9fb0c3 !important;
            border-radius: 8px !important;
            min-height: 76px !important;
        }

        div[data-testid="stFileUploader"] *,
        section[data-testid="stFileUploaderDropzone"] *,
        div[data-testid="stFileUploaderDropzone"] * {
            color: #172033 !important;
        }

        div[data-testid="stFileUploader"] button,
        section[data-testid="stFileUploaderDropzone"] button,
        div[data-testid="stFileUploaderDropzone"] button,
        button[data-testid="baseButton-secondary"] {
            background: #eef7f9 !important;
            border: 1px solid #b8dfe6 !important;
            color: #0f5e73 !important;
            border-radius: 8px !important;
            font-weight: 800 !important;
        }

        div[data-testid="stFileUploader"] svg,
        section[data-testid="stFileUploaderDropzone"] svg,
        div[data-testid="stFileUploaderDropzone"] svg {
            color: #0f5e73 !important;
            fill: #0f5e73 !important;
        }

        div[data-testid="stFileUploaderFile"] {
            background: #f8fafc !important;
            border: 1px solid #d9e0ea !important;
            color: #172033 !important;
        }

        .stButton button {
            border-radius: 8px !important;
            font-weight: 800 !important;
            min-height: 46px !important;
        }

        .stButton button[kind="primary"] {
            background: #0f5e73 !important;
            border-color: #0f5e73 !important;
            color: #ffffff !important;
        }

        .stButton button:not([kind="primary"]) {
            background: #ffffff !important;
            border-color: #c8d2df !important;
            color: #172033 !important;
        }

        div[data-testid="stFormSubmitButton"] button {
            background: #0f5e73 !important;
            border-color: #0f5e73 !important;
            color: #ffffff !important;
            border-radius: 8px !important;
            font-weight: 800 !important;
        }

        div[data-testid="stFormSubmitButton"] button:disabled,
        .stButton button:disabled {
            background: #d6e3ea !important;
            border-color: #c2d0da !important;
            color: #607284 !important;
            opacity: 1 !important;
        }

        .app-header {
            border: 1px solid var(--line);
            border-radius: 8px;
            padding: 18px 20px;
            background:
                linear-gradient(135deg, rgba(255,255,255,0.95) 0%, rgba(232,245,247,0.95) 55%, rgba(255,244,223,0.8) 100%);
            margin-bottom: 14px;
        }

        .sidebar-brand {
            background: #ffffff;
            border: 1px solid var(--line);
            border-left: 5px solid #0f5e73;
            border-radius: 8px;
            padding: 14px 14px 13px 14px;
            margin: 4px 0 16px 0;
            box-shadow: 0 10px 24px rgba(15, 34, 52, 0.06);
        }

        .sidebar-title {
            color: #172033 !important;
            font-size: 17px;
            font-weight: 900;
            line-height: 1.2;
            margin-bottom: 5px;
        }

        .sidebar-subtitle {
            color: #667085 !important;
            font-size: 12px;
            font-weight: 650;
            line-height: 1.45;
        }

        .sidebar-section-card {
            background: #ffffff;
            border: 1px solid var(--line);
            border-left: 5px solid #0f5e73;
            border-radius: 8px;
            padding: 12px 13px;
            margin-top: 16px;
        }

        .sidebar-section-card-title {
            color: #172033 !important;
            font-size: 13px;
            font-weight: 900;
            margin-bottom: 4px;
        }

        .sidebar-section-card-text {
            color: #667085 !important;
            font-size: 12px;
            font-weight: 650;
            line-height: 1.45;
        }

        .section-banner {
            background: #ffffff;
            border: 1px solid var(--line);
            border-left: 6px solid #0f5e73;
            border-radius: 8px;
            padding: 15px 17px;
            margin: 4px 0 18px 0;
            box-shadow: 0 10px 24px rgba(15, 34, 52, 0.05);
        }

        .section-banner-title {
            color: #172033 !important;
            font-size: 21px;
            line-height: 1.25;
            font-weight: 900;
            margin-bottom: 4px;
        }

        .section-banner-copy {
            color: #46586f !important;
            font-size: 13px;
            font-weight: 650;
            line-height: 1.45;
        }

        .eyebrow {
            color: var(--brand);
            font-size: 12px;
            font-weight: 800;
            letter-spacing: 0;
            text-transform: uppercase;
            margin-bottom: 6px;
        }

        .app-title {
            color: #172033 !important;
            font-size: 26px;
            line-height: 1.15;
            font-weight: 800;
            margin: 0;
        }

        .app-subtitle {
            color: #46586f !important;
            font-size: 15px;
            margin-top: 8px;
            max-width: 920px;
        }

        .section-title {
            color: #172033 !important;
            font-size: 18px;
            font-weight: 800;
            margin: 8px 0 10px 0;
        }

        .panel {
            background: var(--surface);
            border: 1px solid var(--line);
            border-radius: 8px;
            padding: 16px;
            margin: 10px 0;
        }

        .profile-name {
            color: var(--ink);
            font-size: 21px;
            font-weight: 800;
            margin-bottom: 2px;
        }

        .profile-id {
            color: var(--muted);
            font-size: 13px;
            font-weight: 700;
            margin-bottom: 12px;
        }

        .kv-grid {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 8px 18px;
        }

        .kv-label {
            color: var(--muted);
            font-size: 12px;
            font-weight: 700;
            text-transform: uppercase;
        }

        .kv-value {
            color: var(--ink);
            font-size: 14px;
            font-weight: 650;
            overflow-wrap: anywhere;
        }

        .status {
            border-radius: 8px;
            padding: 14px 16px;
            font-weight: 750;
            margin: 12px 0;
            border: 1px solid;
        }

        .status-success {
            background: var(--success-soft);
            color: var(--success);
            border-color: #a7e3c2;
        }

        .status-warning {
            background: var(--warning-soft);
            color: var(--warning);
            border-color: #ffd891;
        }

        .status-danger {
            background: var(--danger-soft);
            color: var(--danger);
            border-color: #ffb8b0;
        }

        .status-neutral {
            background: var(--brand-soft);
            color: var(--brand);
            border-color: #b8e4ea;
        }

        .evidence-label {
            color: var(--ink);
            font-size: 14px;
            font-weight: 800;
            margin-bottom: 8px;
        }

        .caption-text {
            color: var(--muted);
            font-size: 12px;
            margin-top: 4px;
        }

        .risk-card {
            background: var(--surface);
            border: 1px solid var(--line);
            border-radius: 8px;
            padding: 16px;
            margin: 12px 0;
        }

        .risk-score {
            color: var(--ink);
            font-size: 34px;
            line-height: 1;
            font-weight: 850;
        }

        .risk-meta {
            color: var(--muted);
            font-size: 13px;
            font-weight: 750;
            margin-top: 5px;
        }

        .risk-chip {
            display: inline-block;
            border-radius: 999px;
            padding: 5px 10px;
            font-size: 12px;
            font-weight: 850;
            margin-top: 10px;
        }

        .risk-low {
            background: var(--success-soft);
            color: var(--success);
        }

        .risk-medium {
            background: var(--warning-soft);
            color: var(--warning);
        }

        .risk-high {
            background: var(--danger-soft);
            color: var(--danger);
        }

        div[data-testid="stExpander"],
        div[data-testid="stExpander"] details {
            background: #ffffff !important;
            border: 1px solid var(--line) !important;
            border-radius: 8px !important;
            color: #172033 !important;
            overflow: hidden !important;
        }

        div[data-testid="stExpander"] summary {
            background: #ffffff !important;
            color: #172033 !important;
            border-bottom: 1px solid var(--line) !important;
            font-weight: 800 !important;
        }

        div[data-testid="stExpander"] summary:hover {
            background: var(--brand-soft) !important;
        }

        div[data-testid="stExpander"] *,
        div[data-testid="stExpander"] svg {
            color: #172033 !important;
            fill: #172033 !important;
        }

        .admin-table-wrap {
            width: 100%;
            overflow-x: auto;
            background: #ffffff;
            border: 1px solid var(--line);
            border-radius: 8px;
        }

        .admin-table {
            width: 100%;
            min-width: 1180px;
            border-collapse: collapse;
            background: #ffffff;
            color: #172033;
            font-size: 13px;
        }

        .admin-table th {
            background: #eef7f9;
            color: #0f5e73;
            font-weight: 850;
            text-align: left;
            border-bottom: 1px solid var(--line);
            padding: 10px 12px;
            white-space: nowrap;
        }

        .admin-table td {
            background: #ffffff;
            color: #172033;
            border-bottom: 1px solid #edf1f6;
            padding: 9px 12px;
            white-space: nowrap;
        }

        .admin-table tr:nth-child(even) td {
            background: #f8fafc;
        }

        .admin-table tr:hover td {
            background: #e8f5f7;
        }

        .identity-results-table {
            min-width: 1900px;
            table-layout: auto;
        }

        .identity-results-table th:first-child,
        .identity-results-table td:first-child {
            min-width: 230px;
            width: 230px;
            text-align: center;
        }

        .identity-results-table td:first-child {
            vertical-align: middle;
        }

        .identity-results-table td:first-child img {
            width: 190px !important;
            height: 190px !important;
            max-width: none !important;
            object-fit: contain !important;
            display: block;
            margin: 0 auto;
            background: #ffffff;
        }

        .table-link {
            color: #0f5e73 !important;
            font-weight: 750;
            text-decoration: none;
        }

        .table-link:hover {
            text-decoration: underline;
        }

        .news-brief {
            background: linear-gradient(135deg, #ffffff 0%, #eef7f9 100%);
            border: 1px solid var(--line);
            border-radius: 8px;
            padding: 18px 20px;
            margin: 8px 0 16px 0;
        }

        .news-brief-title {
            color: #172033;
            font-size: 22px;
            font-weight: 850;
            line-height: 1.25;
            margin-bottom: 6px;
        }

        .news-brief-subtitle {
            color: #46586f;
            font-size: 13px;
            font-weight: 650;
        }

        .news-search-action-spacer {
            height: 28px;
        }

        .news-card {
            background: #ffffff;
            border: 1px solid var(--line);
            border-radius: 8px;
            padding: 13px 14px;
            margin: 9px 0 7px 0;
            min-height: 116px;
            overflow: hidden;
        }

        .news-card-title {
            color: #172033;
            font-size: 14px;
            font-weight: 850;
            line-height: 1.3;
            margin-bottom: 7px;
            display: -webkit-box;
            -webkit-line-clamp: 2;
            -webkit-box-orient: vertical;
            overflow: hidden;
        }

        .news-card-meta {
            color: #667085;
            font-size: 12px;
            font-weight: 700;
            line-height: 1.4;
            display: -webkit-box;
            -webkit-line-clamp: 2;
            -webkit-box-orient: vertical;
            overflow: hidden;
        }

        .news-card-summary {
            color: #46586f;
            font-size: 13px;
            line-height: 1.45;
            margin-top: 8px;
        }

        .news-stat-grid {
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 10px;
            margin: 12px 0 6px 0;
        }

        .news-stat {
            background: #f8fafc;
            border: 1px solid #edf1f6;
            border-radius: 8px;
            padding: 10px 12px;
        }

        .news-stat-label {
            color: #667085;
            font-size: 11px;
            font-weight: 800;
            text-transform: uppercase;
        }

        .news-stat-value {
            color: #172033;
            font-size: 18px;
            font-weight: 850;
            margin-top: 3px;
        }

        .news-chip {
            display: inline-block;
            margin: 4px 6px 4px 0;
            padding: 6px 10px;
            border-radius: 999px;
            border: 1px solid #b8dfe6;
            background: #eef7f9;
            color: #0f5e73;
            font-size: 12px;
            font-weight: 800;
        }

        .news-chip-muted {
            color: #667085;
            font-weight: 700;
        }

        .keyword-chip-row {
            display: flex;
            flex-wrap: nowrap;
            gap: 8px;
            overflow-x: auto;
            padding: 4px 0 8px 0;
            margin-top: -4px;
        }

        .keyword-chip {
            flex: 0 0 auto;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            min-height: 30px;
            padding: 5px 11px;
            border-radius: 999px;
            border: 1px solid #b8dfe6;
            background: #ffffff;
            color: #0f5e73 !important;
            font-size: 12px;
            font-weight: 850;
            text-decoration: none;
            white-space: nowrap;
        }

        .keyword-chip:hover {
            background: #e8f5f7;
            text-decoration: none;
        }

        div[data-testid="stMarkdownContainer"]:has(.keyword-chip-marker) + div [data-testid="column"] {
            width: auto !important;
            flex: 0 0 auto !important;
        }

        div[data-testid="stMarkdownContainer"]:has(.keyword-chip-marker) + div .stButton button {
            min-height: 30px !important;
            height: 30px !important;
            padding: 4px 10px !important;
            border-radius: 999px !important;
            font-size: 12px !important;
            font-weight: 850 !important;
            white-space: nowrap !important;
            background: #ffffff !important;
            border: 1px solid #b8dfe6 !important;
            color: #0f5e73 !important;
        }

        .news-source-list {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 8px;
            margin-top: 6px;
        }

        .news-source-item {
            background: #f8fafc;
            border: 1px solid #edf1f6;
            border-radius: 8px;
            padding: 10px 11px;
            min-height: 66px;
        }

        .news-source-name {
            color: #172033;
            font-size: 13px;
            font-weight: 850;
            overflow-wrap: anywhere;
            display: -webkit-box;
            -webkit-line-clamp: 2;
            -webkit-box-orient: vertical;
            overflow: hidden;
        }

        .news-source-count {
            color: #0f5e73;
            font-size: 12px;
            font-weight: 800;
            margin-top: 3px;
        }

        .news-article {
            background: #ffffff;
            border: 1px solid #d9e0ea;
            border-radius: 8px;
            padding: 14px;
            margin: 10px 0;
        }

        .news-article-title {
            color: #172033;
            font-size: 15px;
            font-weight: 850;
            line-height: 1.35;
            margin-bottom: 7px;
        }

        .news-article-body {
            color: #46586f;
            font-size: 13px;
            line-height: 1.5;
            margin-top: 8px;
        }

        .status-chip {
            display: inline-block;
            border-radius: 999px;
            padding: 5px 10px;
            font-size: 12px;
            font-weight: 850;
            border: 1px solid;
            margin-left: 8px;
        }

        .status-chip-pending {
            background: var(--brand-soft);
            color: var(--brand);
            border-color: #b8e4ea;
        }

        .status-chip-processing {
            background: var(--warning-soft);
            color: var(--warning);
            border-color: #ffd891;
        }

        .status-chip-completed {
            background: var(--success-soft);
            color: var(--success);
            border-color: #a7e3c2;
        }


        .drishti-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
            gap: 12px;
            margin: 12px 0 16px 0;
        }

        .drishti-card {
            background: #ffffff;
            border: 1px solid #d9e0ea;
            border-left: 5px solid #7c3aed;
            border-radius: 8px;
            padding: 14px;
            min-height: 118px;
            box-shadow: 0 8px 22px rgba(15, 34, 52, 0.05);
        }

        .drishti-card-title {
            color: #172033 !important;
            font-size: 14px;
            font-weight: 900;
            line-height: 1.3;
            margin-bottom: 7px;
        }

        .drishti-card-meta,
        .drishti-card-body {
            color: #46586f !important;
            font-size: 12px;
            font-weight: 650;
            line-height: 1.45;
            margin-top: 5px;
        }

        .drishti-chip {
            display: inline-block;
            border-radius: 999px;
            padding: 4px 9px;
            margin: 3px 5px 3px 0;
            background: #f4f7fb;
            border: 1px solid #d9e0ea;
            color: #334155 !important;
            font-size: 11px;
            font-weight: 850;
        }

        .drishti-chip-good {
            background: #e7f8ef;
            border-color: #a7e3c2;
            color: #087443 !important;
        }

        .drishti-chip-warn {
            background: #fff4df;
            border-color: #ffd891;
            color: #9a5b00 !important;
        }

        .drishti-chip-bad {
            background: #fff0ee;
            border-color: #ffb8b0;
            color: #b42318 !important;
        }

        .drishti-flow {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
            gap: 10px;
            margin: 10px 0 16px 0;
        }

        .drishti-flow-step,
        .drishti-draft {
            background: #ffffff;
            border: 1px solid #d9e0ea;
            border-radius: 8px;
            padding: 12px;
            min-height: 92px;
        }

        .drishti-draft {
            border-left: 5px solid #0f5e73;
            margin: 10px 0;
        }

        .drishti-flow-label {
            color: #7c3aed !important;
            font-size: 11px;
            font-weight: 900;
            text-transform: uppercase;
            margin-bottom: 5px;
        }

        .drishti-map-row {
            display: grid;
            grid-template-columns: minmax(140px, 1.2fr) minmax(100px, 0.8fr) minmax(100px, 0.8fr) minmax(90px, 0.6fr);
            gap: 8px;
            align-items: center;
            background: #ffffff;
            border: 1px solid #d9e0ea;
            border-radius: 8px;
            padding: 10px 12px;
            margin: 8px 0;
        }
        .status-chip-failed {
            background: var(--danger-soft);
            color: var(--danger);
            border-color: #ffb8b0;
        }
    </style>
    """,
    unsafe_allow_html=True
)


SEARCH_OPTIONS = {
    "Full Name": "full_name",
    "Username": "username",
    "Face Image": "face_image",
    "DOB": "date_of_birth",
    "Aadhaar Number": "aadhar_number",
    "PAN Number": "pan_number",
    "Voter ID Number": "voter_id_number",
    "Driving Licence Number": "driving_license_number",
    "Passport Number": "passport_number",
    "Phone Number": "phone_number",
    "Email": "email",
    "Employee ID": "employee_id",
    "Department": "department",
    "State": "state"
}

OSINT_FIELD_LABELS = {
    value: label
    for label, value in SEARCH_OPTIONS.items()
}

OSINT_ELIGIBLE_FIELDS = set(OSINT_FIELD_LABELS)

NAVIGATION_SECTIONS = [
    {
        "label": "Identity Search",
        "description": "Search records, review matching fields, and submit approved OSINT targets.",
        "accent": "#0f5e73"
    },
    {
        "label": "Document Validation",
        "description": "Validate uploaded government documents with OCR, database checks, and risk scoring.",
        "accent": "#b42318"
    },
    {
        "label": "Face Search",
        "description": "Compare a face image against stored identity photos.",
        "accent": "#2563eb"
    },
    {
        "label": "Admin Operations",
        "description": "Load, create, update, and delete identity records from the database.",
        "accent": "#087443"
    },
    {
        "label": "News Intelligence",
        "description": "Explore top news, related articles, sources, and entities.",
        "accent": "#be185d"
    },
    {
        "label": "DRISHTI Intelligence",
        "description": "Design preview for acquisition, search, narratives, graph, heatmaps, GPU readiness, and content operations.",
        "accent": "#7c3aed"
    }
]

NAVIGATION_LABELS = [
    section["label"]
    for section in NAVIGATION_SECTIONS
]

DB_FIELD_LABELS = {
    "employee_id": "Employee ID",
    "full_name": "Full Name",
    "date_of_birth": "DOB",
    "aadhar_number": "Aadhaar Number",
    "pan_number": "PAN Number",
    "voter_id_number": "Voter ID Number",
    "driving_license_number": "Driving Licence Number",
    "passport_number": "Passport Number",
    "phone_number": "Phone Number",
    "email": "Email",
    "department": "Department",
    "state": "State",
    "username": "Username"
}

DOCUMENT_OPTIONS = {
    "Aadhaar Card": "aadhaar",
    "PAN Card": "pan",
    "Voter ID Card": "voter_id",
    "Driving Licence": "driving_license",
    "Passport": "passport"
}

DOCUMENT_FIELD_BY_TYPE = {
    "aadhaar": "aadhar_number",
    "pan": "pan_number",
    "voter_id": "voter_id_number",
    "driving_license": "driving_license_number",
    "passport": "passport_number"
}

REVIEW_UPDATE_FIELDS = [
    ("Full Name", "full_name"),
    ("Date of Birth", "date_of_birth"),
    ("Aadhaar Number", "aadhar_number"),
    ("PAN Number", "pan_number"),
    ("Voter ID Number", "voter_id_number"),
    ("Driving Licence Number", "driving_license_number"),
    ("Passport Number", "passport_number"),
    ("Phone Number", "phone_number"),
    ("Email", "email"),
    ("Department", "department"),
    ("State", "state")
]


def infer_document_label_from_filename(filename):
    """Guess document type from uploaded filename to reduce manual selection."""

    normalized_name = (filename or "").lower()
    guesses = [
        (("aadhaar", "aadhar", "uid"), "Aadhaar Card"),
        (("passport",), "Passport"),
        (("driving", "licence", "license", "dl"), "Driving Licence"),
        (("voter", "vid"), "Voter ID Card"),
        (("pan",), "PAN Card")
    ]

    for tokens, label in guesses:
        if any(token in normalized_name for token in tokens):
            return label

    return "Aadhaar Card"


def escaped_cell(value):
    """Escape a value for HTML table output and show '-' for blanks."""

    if value is None or value == "":
        return "-"
    return html.escape(str(value))


def nested_value(item, path):
    """Read nested dictionary values using dot paths like `extracted_data.bio`."""

    current_value = item

    for part in path.split("."):
        if not isinstance(current_value, dict):
            return None

        current_value = current_value.get(part)

    return current_value


def formatted_table_cell(value):
    """Format arbitrary values for dashboard HTML tables."""

    if value is None or value == "":
        return "-"

    if is_base64_like_value(value):
        return "[hidden base64 data]"

    if isinstance(value, list):
        if not value:
            return "-"

        if all(not isinstance(item, (dict, list)) for item in value):
            value = ", ".join(str(item) for item in value)
        else:
            value = json.dumps(value, ensure_ascii=False)

    if isinstance(value, dict):
        image_html = avatar_image_html(
            value.get("image_path"),
            value.get("image_url"),
            size=value.get("image_size") or 128,
            object_fit=value.get("image_fit") or "cover"
        )

        if image_html:
            return image_html

        if "image_path" in value or "image_url" in value:
            return "-"

        value = json.dumps(value, ensure_ascii=False)

    value = str(value)
    image_html = local_image_html(value)

    if image_html:
        return image_html

    escaped_value = html.escape(value)

    if value.startswith(("http://", "https://")):
        return (
            f'<a class="table-link" href="{escaped_value}" '
            'target="_blank" rel="noopener noreferrer">View</a>'
        )

    if "\n" in value:
        return escaped_value.replace("\n", "<br>")

    return escaped_value


def local_image_html(
    value,
    size=128,
    object_fit="cover"
):
    """Render a local decoded OSINT image path as a safe HTML thumbnail."""

    if not isinstance(value, str):
        return ""

    if not value.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
        return ""

    image_info = local_image_info(value)

    if not image_info:
        return ""

    resolved_path = image_info["path"]
    mime_type = image_info["mime_type"]

    with open(resolved_path, "rb") as image_file:
        encoded_image = base64.b64encode(image_file.read()).decode("ascii")

    return (
        f'<img src="data:{mime_type};base64,{encoded_image}" '
        'alt="OSINT avatar image" '
        f'style="width:{int(size)}px;height:{int(size)}px;object-fit:{html.escape(str(object_fit))};border-radius:10px;'
        'border:1px solid #d8e3ec;" />'
    )


def remote_image_html(
    value,
    size=128,
    object_fit="cover"
):
    """Render a remote avatar URL as a dashboard thumbnail."""

    if not isinstance(value, str):
        return ""

    if not value.startswith(("http://", "https://")):
        return ""

    escaped_value = html.escape(value)

    return (
        f'<a href="{escaped_value}" target="_blank" rel="noopener noreferrer">'
        f'<img src="{escaped_value}" alt="Avatar image" '
        "onerror=\"this.closest('a').replaceWith(document.createTextNode('-'))\" "
        f'style="width:{int(size)}px;height:{int(size)}px;object-fit:{html.escape(str(object_fit))};border-radius:10px;'
        'border:1px solid #d8e3ec;background:#ffffff;" />'
        '</a>'
    )


def avatar_image_html(
    image_path=None,
    image_url=None,
    size=128,
    object_fit="cover"
):
    """Prefer validated local avatar images, then fall back to remote URLs."""

    return (
        local_image_html(
            image_path,
            size=size,
            object_fit=object_fit
        )
        or remote_image_html(
            image_url,
            size=size,
            object_fit=object_fit
        )
    )


def local_image_info(image_path):
    """Resolve and validate a local image, returning its real MIME type."""

    if not image_path:
        return None

    if not str(image_path).lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
        return None

    try:
        resolved_path = resolve_photo_path(image_path)
    except NameError:
        return None

    if not resolved_path or not os.path.exists(resolved_path):
        return None

    try:
        with Image.open(resolved_path) as image:
            image.verify()
            image_format = (image.format or "").upper()
    except (OSError, UnidentifiedImageError, ValueError):
        return None

    mime_types = {
        "JPEG": "image/jpeg",
        "JPG": "image/jpeg",
        "PNG": "image/png",
        "WEBP": "image/webp"
    }
    mime_type = mime_types.get(image_format)

    if not mime_type:
        return None

    return {
        "path": resolved_path,
        "mime_type": mime_type
    }


def local_image_path_exists(image_path):
    """Return True when a local avatar path resolves to an existing image."""

    return bool(local_image_info(image_path))


def avatar_row_has_usable_image(row):
    """Return True only for rows with an existing local image or remote image URL."""

    if not isinstance(row, dict):
        return False

    image_path = row.get("avatar_path")
    image_url = (
        row.get("avatar_url")
        or extract_avatar_url(row.get("enriched_data") or row)
    )

    return local_image_path_exists(image_path)


def avatar_image_value(row):
    """Build an avatar display value from a normalized or raw OSINT row."""

    if not isinstance(row, dict):
        return None

    image_path = row.get("avatar_path")
    image_url = (
        row.get("avatar_url")
        or extract_avatar_url(row.get("enriched_data") or row)
    )

    if not local_image_path_exists(image_path):
        image_path = None

    if not str(image_url or "").startswith(("http://", "https://")):
        image_url = None

    if not image_path and not image_url:
        return None

    return {
        "image_path": image_path,
        "image_url": image_url
    }


def is_base64_like_value(value):
    """Return True for large image/base64 blobs that should not be displayed."""

    if not isinstance(value, str):
        return False

    stripped_value = value.strip()

    if stripped_value.startswith("data:image"):
        return True

    if len(stripped_value) < 120:
        return False

    compact_value = stripped_value.replace("\n", "").replace("\r", "")

    if compact_value.startswith(("/9j/", "iVBOR", "AAAA")):
        return True

    allowed_characters = set(
        "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/="
    )

    return all(character in allowed_characters for character in compact_value[:240])


def render_light_table(rows, columns, empty_message, table_class="admin-table"):
    """Render a reusable themed table from rows and column accessors."""

    header_cells = "".join(
        f"<th>{html.escape(label)}</th>"
        for label, _ in columns
    )
    body_rows = []

    for row in rows or []:
        cells = []

        for _, accessor in columns:
            if callable(accessor):
                value = accessor(row)
            else:
                value = nested_value(row, accessor)

            cells.append(f"<td>{formatted_table_cell(value)}</td>")

        body_rows.append(f"<tr>{''.join(cells)}</tr>")

    if not body_rows:
        body_rows.append(
            f'<tr><td colspan="{len(columns)}">{html.escape(empty_message)}</td></tr>'
        )

    st.markdown(
        f"""
        <div class="admin-table-wrap">
            <table class="{html.escape(table_class)}">
                <thead><tr>{header_cells}</tr></thead>
                <tbody>{''.join(body_rows)}</tbody>
            </table>
        </div>
        """,
        unsafe_allow_html=True
    )


def render_admin_records_table(records):
    """Render the loaded identity records table in the admin tab."""

    columns = [
        ("Employee ID", "employee_id"),
        ("Full Name", "full_name"),
        ("DOB", "date_of_birth"),
        ("Aadhaar", "aadhar_number"),
        ("PAN", "pan_number"),
        ("Voter ID", "voter_id_number"),
        ("Driving Licence", "driving_license_number"),
        ("Passport", "passport_number"),
        ("Phone", "phone_number"),
        ("Email", "email"),
        ("Department", "department"),
        ("State", "state")
    ]

    header_cells = "".join(
        f"<th>{html.escape(label)}</th>"
        for label, _ in columns
    )
    body_rows = []

    for record in records:
        cells = "".join(
            f"<td>{escaped_cell(record.get(field))}</td>"
            for _, field in columns
        )
        body_rows.append(f"<tr>{cells}</tr>")

    if not body_rows:
        body_rows.append(
            f'<tr><td colspan="{len(columns)}">No identity records found.</td></tr>'
        )

    st.markdown(
        f"""
        <div class="admin-table-wrap">
            <table class="admin-table">
                <thead><tr>{header_cells}</tr></thead>
                <tbody>{''.join(body_rows)}</tbody>
            </table>
        </div>
        """,
        unsafe_allow_html=True
    )



def drishti_chip(label, tone="neutral"):
    tone_class = {
        "good": "drishti-chip-good",
        "warn": "drishti-chip-warn",
        "bad": "drishti-chip-bad",
        "neutral": ""
    }.get(tone, "")
    return f'<span class="drishti-chip {tone_class}">{html.escape(str(label or "-"))}</span>'


def render_drishti_metric_row(metrics):
    metric_cols = st.columns(6)
    metric_cols[0].metric("Posts", metrics.get("posts_analyzed", 0))
    metric_cols[1].metric("Alerts", metrics.get("alerts_triggered", 0))
    metric_cols[2].metric("Negative", metrics.get("negative", 0))
    metric_cols[3].metric("Neutral", metrics.get("neutral", 0))
    metric_cols[4].metric("Positive", metrics.get("positive", 0))
    metric_cols[5].metric("Languages", metrics.get("languages", 0))


def render_drishti_cards(title, items, label_key="label", value_key="count"):
    st.markdown(f'<div class="section-title">{html.escape(title)}</div>', unsafe_allow_html=True)
    cards = []
    for item in items[:12]:
        cards.append(
            '<div class="drishti-card">'
            f'<div class="drishti-card-title">{html.escape(str(item.get(label_key) or "-"))}</div>'
            f'<div class="news-stat-value">{html.escape(str(item.get(value_key) or 0))}</div>'
            '</div>'
        )
    if cards:
        st.markdown(f'<div class="drishti-grid">{"".join(cards)}</div>', unsafe_allow_html=True)
    else:
        status_panel("No data available.", "neutral")


def render_drishti_distribution(title, mapping):
    rows = [
        {"label": key, "count": value}
        for key, value in sorted((mapping or {}).items(), key=lambda item: str(item[0]))
    ]
    render_drishti_cards(title, rows)


def render_drishti_implementation_map():
    st.markdown('<div class="section-title">Client Demo Implementation Map</div>', unsafe_allow_html=True)
    flow_steps = [
        ("Acquire", "20-minute refresh, automatic retry, alternate crawler path, source/CAPTCHA flags"),
        ("Search", "Boolean, phrase, wildcard, multilingual, location and emotion filters"),
        ("Understand", "Sentiment, emotion, fault line, stance, risk and narrative summarization"),
        ("Visualize", "Knowledge graph relationships and heatmap-ready geo points"),
        ("Deploy", "Cloud GPU ready, no OpenAI dependency, Docker/Kubernetes target"),
        ("Operate", "Review-first content generation to create/change a narrative")
    ]
    flow_html = []
    for index, (label, body) in enumerate(flow_steps, start=1):
        flow_html.append(
            '<div class="drishti-flow-step">'
            f'<div class="drishti-flow-label">Step {index}</div>'
            f'<div class="drishti-card-title">{html.escape(label)}</div>'
            f'<div class="drishti-card-body">{html.escape(body)}</div>'
            '</div>'
        )
    st.markdown(f'<div class="drishti-flow">{"".join(flow_html)}</div>', unsafe_allow_html=True)


def render_drishti_source_cards(acquisition):
    cards = []
    for source in acquisition.get("sources") or []:
        status = str(source.get("status") or "unknown")
        tone = "good" if status == "available" else "bad" if "captcha" in status or "unavailable" in status else "warn"
        accent = "#087443" if tone == "good" else "#b42318" if tone == "bad" else "#9a5b00"
        cards.append(
            f'<div class="drishti-card" style="border-left-color: {accent};">'
            f'<div class="drishti-card-title">{html.escape(str(source.get("name") or "Source"))}</div>'
            f'{drishti_chip(status.replace("_", " ").title(), tone)}'
            f'{drishti_chip(str(source.get("type") or "source").replace("_", " ").title())}'
            f'<div class="drishti-card-meta">Attempts: {html.escape(str(source.get("attempts") or 0))}</div>'
            f'<div class="drishti-card-body">Alternate path: {html.escape(str(source.get("alternate") or "-"))}</div>'
            f'<div class="drishti-card-body">{html.escape(str(source.get("last_error") or "No active source error."))}</div>'
            '</div>'
        )
    st.markdown(f'<div class="drishti-grid">{"".join(cards)}</div>', unsafe_allow_html=True)


def render_drishti_narratives(narratives):
    cards = []
    for card in (narratives or [])[:12]:
        risk = float(card.get("risk_score") or 0)
        tone = "bad" if risk >= 0.7 else "warn" if risk >= 0.5 else "good"
        accent = "#b42318" if tone == "bad" else "#9a5b00" if tone == "warn" else "#087443"
        sub_html = "".join(drishti_chip(item) for item in card.get("sub_narratives", [])[:4])
        cards.append(
            f'<div class="drishti-card" style="border-left-color: {accent};">'
            f'<div class="drishti-card-title">{html.escape(str(card.get("narrative") or "Narrative"))}</div>'
            f'{drishti_chip("Risk " + str(card.get("risk_score", 0)), tone)}'
            f'{drishti_chip("Confidence " + str(card.get("confidence", 0)))}'
            f'{drishti_chip(str(card.get("stance") or "Neutral"))}'
            f'<div class="drishti-card-meta">Fault line: {html.escape(str(card.get("fault_line") or "-"))}</div>'
            f'<div class="drishti-card-body">{html.escape(str(card.get("summary") or "No summary available."))}</div>'
            f'<div class="drishti-card-body">Prediction: {html.escape(str(card.get("risk_prediction") or "-"))}</div>'
            f'<div class="drishti-card-body">{sub_html}</div>'
            '</div>'
        )
    if cards:
        st.markdown(f'<div class="drishti-grid">{"".join(cards)}</div>', unsafe_allow_html=True)
    else:
        status_panel("No narrative intelligence is available yet.", "neutral")


def render_drishti_search_results(search_payload):
    results = search_payload.get("results") or []
    cards = []
    for row in results[:12]:
        risk = float(row.get("risk_score") or 0)
        tone = "bad" if risk >= 0.7 else "warn" if risk >= 0.5 else "good"
        accent = "#b42318" if tone == "bad" else "#9a5b00" if tone == "warn" else "#087443"
        cards.append(
            f'<div class="drishti-card" style="border-left-color: {accent};">'
            f'<div class="drishti-card-title">{html.escape(str(row.get("narrative") or row.get("id") or "Result"))}</div>'
            f'{drishti_chip(str(row.get("source") or "Source"))}'
            f'{drishti_chip(str(row.get("location") or "Location"))}'
            f'{drishti_chip(str(row.get("emotion") or "Emotion"))}'
            f'{drishti_chip(str(row.get("sentiment") or "Sentiment"))}'
            f'{drishti_chip("Risk " + str(row.get("risk_score") or 0), tone)}'
            f'<div class="drishti-card-body">{html.escape(str(row.get("translated_text") or row.get("text") or ""))[:520]}</div>'
            '</div>'
        )
    if cards:
        st.markdown(f'<div class="drishti-grid">{"".join(cards)}</div>', unsafe_allow_html=True)
    else:
        status_panel("No DRISHTI records matched this search.", "warning")


def render_drishti_heatmap_points(points):
    rows = []
    for point in (points or [])[:12]:
        risk = float(point.get("risk_score") or 0)
        tone = "bad" if risk >= 0.7 else "warn" if risk >= 0.5 else "good"
        rows.append(
            '<div class="drishti-map-row">'
            f'<div><strong>{html.escape(str(point.get("location") or "-"))}</strong></div>'
            f'<div>{html.escape(str(point.get("sentiment") or "Neutral"))}</div>'
            f'<div>{drishti_chip("Risk " + str(point.get("risk_score") or 0), tone)}</div>'
            f'<div>{html.escape(str(point.get("lat") or "-"))}, {html.escape(str(point.get("lon") or "-"))}</div>'
            '</div>'
        )
    st.markdown("".join(rows), unsafe_allow_html=True) if rows else status_panel("No heatmap points available.", "neutral")


def render_drishti_graph_edges(graph):
    cards = []
    for edge in ((graph or {}).get("edges") or [])[:12]:
        cards.append(
            '<div class="drishti-card">'
            f'<div class="drishti-card-title">{html.escape(str(edge.get("source") or "-"))}</div>'
            f'{drishti_chip(str(edge.get("relation") or "related"))}'
            f'<div class="drishti-card-body">Target: {html.escape(str(edge.get("target") or "-"))}</div>'
            '</div>'
        )
    st.markdown(f'<div class="drishti-grid">{"".join(cards)}</div>', unsafe_allow_html=True) if cards else status_panel("No graph edges available.", "neutral")


def render_drishti_deployment_cards(deployment):
    deployment = deployment or {}
    rows = [
        ("Cloud GPU Ready", "Ready" if deployment.get("cloud_gpu_ready") else "Pending", "good" if deployment.get("cloud_gpu_ready") else "warn"),
        ("OpenAI Dependency", "No" if not deployment.get("openai_dependency") else "Yes", "good" if not deployment.get("openai_dependency") else "warn"),
        ("Model Runtime", deployment.get("model_runtime") or "Pluggable local/GPU LLM endpoint", "neutral"),
        ("Deployment Target", deployment.get("container_target") or "Docker/Kubernetes", "neutral")
    ]
    cards = []
    for title, value, tone in rows:
        cards.append(
            '<div class="drishti-card">'
            f'<div class="drishti-card-title">{html.escape(str(title))}</div>'
            f'{drishti_chip(value, tone)}'
            '</div>'
        )
    st.markdown(f'<div class="drishti-grid">{"".join(cards)}</div>', unsafe_allow_html=True)



def render_drishti_platform_fetch_table(acquisition):
    """Render platform-level fetch status, retry, alternate crawler, and CAPTCHA flags."""

    rows = []
    for source in acquisition.get("sources") or []:
        status = str(source.get("status") or "unknown")
        last_error = str(source.get("last_error") or "")
        if "captcha" in status.lower() or "captcha" in last_error.lower():
            resolution = "Data cannot be fetched/resolved because CAPTCHA is unresolved. Route to manual review or alternate provider."
        elif status == "available":
            resolution = "Data fetch available through configured source path."
        elif "unavailable" in status.lower():
            resolution = "Source unavailable. Use alternate crawler/provider and retry on next refresh."
        else:
            resolution = "Retry automatically and use alternate crawler path if source remains blocked."
        rows.append({
            "platform": source.get("name") or "-",
            "source_type": str(source.get("type") or "-").replace("_", " ").title(),
            "fetch_status": status.replace("_", " ").title(),
            "attempts": source.get("attempts") or 0,
            "alternate": source.get("alternate") or "-",
            "issue": last_error or "-",
            "resolution": resolution
        })

    render_light_table(
        rows,
        [
            ("Platform", "platform"),
            ("Type", "source_type"),
            ("Fetch Status", "fetch_status"),
            ("Attempts", "attempts"),
            ("Alternate Crawler / Provider", "alternate"),
            ("Issue", "issue"),
            ("Resolution", "resolution")
        ],
        "No platform fetch status records available."
    )


def render_drishti_osint_job_loader():
    """Expose the existing OSINT job lookup workflow inside DRISHTI."""

    st.markdown('<div class="section-title">OSINT Job Load</div>', unsafe_allow_html=True)
    status_panel("Load an existing OSINT job here to demonstrate how DRISHTI can reuse identity-search OSINT evidence.", "neutral")
    render_osint_job_lookup_panel()
    loaded_job = st.session_state.get("last_osint_job")
    if loaded_job:
        st.markdown('<div class="section-title">Loaded OSINT Job Evidence</div>', unsafe_allow_html=True)
        render_osint_job_card(loaded_job)
def render_drishti_workspace():
    response, result = get_request(DRISHTI_OVERVIEW_URL)
    if response is None or response.status_code != 200:
        status_panel(result.get("message", "DRISHTI overview could not be loaded."), "danger")
        return

    overview = result.get("overview") or {}
    acquisition = overview.get("acquisition") or {}

    refresh_col, status_col = st.columns([0.8, 2.2])
    with refresh_col:
        if st.button("Refresh Sources", type="primary", use_container_width=True, key="drishti_refresh_sources"):
            refresh_response, refresh_result = post_request(DRISHTI_REFRESH_URL, json_body={})
            if refresh_response is None or refresh_response.status_code != 200:
                status_panel(refresh_result.get("message", "Source refresh failed."), "danger")
            else:
                status_panel("DRISHTI acquisition refresh completed.", "success")
                st.rerun()
    with status_col:
        st.caption(
            f"Refresh every {acquisition.get('refresh_interval_minutes', 20)} minutes. "
            f"Available sources: {acquisition.get('available_sources', 0)}/{acquisition.get('total_sources', 0)}. "
            f"Active data source: {str(overview.get('data_source') or 'default_demo_data').replace('_', ' ').title()}."
        )


    map_tab, acquisition_tab, search_tab, narrative_tab, visual_tab, infrastructure_tab, content_tab = st.tabs([
        "Implementation Map",
        "Acquisition",
        "Search",
        "Narratives",
        "Visual Analytics",
        "Infrastructure",
        "Content Operations"
    ])

    with map_tab:
        render_drishti_implementation_map()
        st.markdown('<div class="section-title">Platform Fetch Resolution</div>', unsafe_allow_html=True)
        render_drishti_platform_fetch_table(acquisition)

    with acquisition_tab:
        st.markdown('<div class="section-title">Data Acquisition & Resilience</div>', unsafe_allow_html=True)
        status_cols = st.columns(4)
        status_cols[0].metric("Refresh Window", f"{acquisition.get('refresh_interval_minutes', 20)} min")
        status_cols[1].metric("Available Sources", f"{acquisition.get('available_sources', 0)}/{acquisition.get('total_sources', 0)}")
        status_cols[2].metric("Flagged Sources", len(acquisition.get("unavailable_sources") or []))
        status_cols[3].metric("Next Refresh", str(acquisition.get("next_refresh") or "-")[:16])
        render_drishti_source_cards(acquisition)
        st.markdown('<div class="section-title">Platform Fetch Resolution</div>', unsafe_allow_html=True)
        render_drishti_platform_fetch_table(acquisition)
        render_drishti_osint_job_loader()

    with search_tab:
        query_col, location_col, emotion_col, language_col = st.columns([2, 1, 1, 1])
        with query_col:
            query = st.text_input("Boolean query", value='"public trust" OR rumour* AND -spam', key="drishti_query")
        with location_col:
            location_options = sorted({point.get("location") for point in overview.get("heatmap", []) if point.get("location")}) or ["Chennai", "Delhi", "Guwahati", "Jaipur", "Pune", "Srinagar"]
            locations = st.multiselect("Location tags", location_options, key="drishti_locations")
        with emotion_col:
            emotions = st.multiselect("Emotion filter", ["Anger", "Fear", "Neutral", "Trust"], key="drishti_emotions")
        with language_col:
            languages = st.multiselect("Languages", ["en", "hi"], key="drishti_languages")
        if st.button("Search DRISHTI", type="primary", use_container_width=True, key="drishti_search_button"):
            search_response, search_result = post_request(DRISHTI_SEARCH_URL, json_body={"query": query, "locations": locations, "emotions": emotions, "languages": languages})
            if search_response is None or search_response.status_code != 200:
                status_panel(search_result.get("message", "DRISHTI search failed."), "danger")
            else:
                st.session_state["drishti_search"] = search_result.get("search") or {}
                status_panel("DRISHTI search completed.", "success")
        search_payload = st.session_state.get("drishti_search") or {}
        if search_payload:
            result_cols = st.columns(3)
            result_cols[0].metric("Matches", search_payload.get("total", 0))
            result_cols[1].metric("Keywords", len(search_payload.get("keyword_recommendations") or []))
            result_cols[2].metric("Data Source", str(search_payload.get("data_source") or "-").replace("_", " ").title())
            render_drishti_search_results(search_payload)
            render_drishti_distribution("Automatic Keyword Recommendations", {item.get("keyword"): item.get("score") for item in search_payload.get("keyword_recommendations", [])})

    with narrative_tab:
        st.markdown('<div class="section-title">Narrative & Sentiment Intelligence</div>', unsafe_allow_html=True)
        render_drishti_narratives(overview.get("narratives") or [])

    with visual_tab:
        st.markdown('<div class="section-title">Visualization & Analytics</div>', unsafe_allow_html=True)
        left_col, right_col = st.columns(2)
        with left_col:
            render_drishti_distribution("Source Breakdown", overview.get("source_breakdown") or {})
            render_drishti_distribution("Sentiment Distribution", overview.get("sentiment_distribution") or {})
        with right_col:
            render_drishti_distribution("Location Tags", overview.get("location_breakdown") or {})
            st.markdown('<div class="section-title">Heat Map Points</div>', unsafe_allow_html=True)
            render_drishti_heatmap_points(overview.get("heatmap") or [])
        st.markdown('<div class="section-title">Knowledge Graph</div>', unsafe_allow_html=True)
        render_drishti_graph_edges(overview.get("knowledge_graph") or {})

    with infrastructure_tab:
        st.markdown('<div class="section-title">Infrastructure Readiness</div>', unsafe_allow_html=True)
        render_drishti_deployment_cards(overview.get("deployment") or {})
        status_panel("Designed for cloud-hosted GPU deployment with pluggable local models and no OpenAI dependency.", "success")

    with content_tab:
        st.markdown('<div class="section-title">Content Operations</div>', unsafe_allow_html=True)
        narrative_options = [card.get("narrative") for card in overview.get("narratives", []) if card.get("narrative")]
        selected_narrative = st.selectbox("Narrative", narrative_options or ["Public trust"], key="drishti_content_narrative")
        content_col, language_col, tone_col, image_col = st.columns([1, 1, 1, 0.8])
        with content_col:
            content_type = st.selectbox("Format", ["Short Post", "Blog", "Article", "Response Comment"], key="drishti_content_type")
        with language_col:
            language = st.selectbox("Language", ["English", "Hindi", "Bilingual"], key="drishti_content_language")
        with tone_col:
            tone = st.selectbox("Tone", ["Calm", "Corrective", "Empathetic", "Urgent"], key="drishti_content_tone")
        with image_col:
            include_image = st.checkbox("Image prompt", key="drishti_include_image")
        if st.button("Generate Content Candidates", type="primary", use_container_width=True, key="drishti_generate_content"):
            generation_response, generation_result = post_request(DRISHTI_CONTENT_URL, json_body={"narrative": selected_narrative, "content_type": content_type, "language": language, "tone": tone, "include_image": include_image})
            if generation_response is None or generation_response.status_code != 200:
                status_panel(generation_result.get("message", "Content generation failed."), "danger")
            else:
                st.session_state["drishti_generation"] = generation_result.get("generation") or {}
                status_panel("Content candidates generated for human review.", "success")
        generation = st.session_state.get("drishti_generation") or {}
        if generation:
            status_panel("Human-in-the-loop review is required before campaign use.", "warning")
            draft_cards = []
            for output in generation.get("outputs", []):
                draft_cards.append(
                    '<div class="drishti-draft">'
                    f'<div class="drishti-card-title">{html.escape(str(output.get("model") or "Candidate"))}</div>'
                    f'{drishti_chip("Confidence " + str(output.get("confidence") or 0), "good")}'
                    f'<div class="drishti-card-body">{html.escape(str(output.get("content") or ""))}</div>'
                    '</div>'
                )
            st.markdown("".join(draft_cards), unsafe_allow_html=True)
            if generation.get("image_prompt"):
                st.text_area("Image prompt", generation.get("image_prompt"), height=90, key="drishti_image_prompt_output")
def render_header():
    """Render the dashboard title and summary header."""

    st.markdown(
        """
        <div class="app-header">
            <div class="eyebrow">Identity Verification Command Center</div>
            <h1 class="app-title">Search, validate, review, and match identities from one secure console</h1>
            <div class="app-subtitle">
                Document OCR, PostgreSQL identity verification, database photo matching, and direct face search
                are connected into one operator-ready workflow.
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )


def navigation_section_meta(section_label):
    """Return display metadata for a dashboard workspace section."""

    for section in NAVIGATION_SECTIONS:
        if section["label"] == section_label:
            return section

    return NAVIGATION_SECTIONS[0]


def render_sidebar_navigation():
    """Render vertical dashboard navigation and return the active section label."""

    st.sidebar.markdown(
        """
        <div class="sidebar-brand">
            <div class="sidebar-title">Identity Search Service</div>
            <div class="sidebar-subtitle">
                Verification, OSINT, admin records, and news intelligence in one operator console.
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    if st.session_state.get("active_dashboard_section") not in NAVIGATION_LABELS:
        st.session_state["active_dashboard_section"] = NAVIGATION_LABELS[0]

    selected_section = st.sidebar.radio(
        "Workspace",
        NAVIGATION_LABELS,
        key="active_dashboard_section"
    )
    section = navigation_section_meta(selected_section)

    st.sidebar.markdown(
        f"""
        <div class="sidebar-section-card" style="border-left-color: {section['accent']};">
            <div class="sidebar-section-card-title">{html.escape(section['label'])}</div>
            <div class="sidebar-section-card-text">{html.escape(section['description'])}</div>
        </div>
        """,
        unsafe_allow_html=True
    )

    return selected_section


def render_active_section_header(section_label):
    """Render a professional page header for the selected dashboard section."""

    section = navigation_section_meta(section_label)
    st.markdown(
        f"""
        <div class="section-banner" style="border-left-color: {section['accent']};">
            <div class="section-banner-title">{html.escape(section['label'])}</div>
            <div class="section-banner-copy">{html.escape(section['description'])}</div>
        </div>
        """,
        unsafe_allow_html=True
    )


def status_panel(message, status="neutral"):
    """Render a dashboard status message with success/warning/error styling."""

    status_class = {
        "success": "status-success",
        "warning": "status-warning",
        "danger": "status-danger",
        "neutral": "status-neutral"
    }.get(status, "status-neutral")

    st.markdown(
        f'<div class="status {status_class}">{message}</div>',
        unsafe_allow_html=True
    )


def resolve_photo_path(photo_path):
    """Resolve stored photo paths into local paths Streamlit can display."""

    if not photo_path:
        return None

    normalized_path = os.path.normpath(str(photo_path))

    if os.path.isabs(normalized_path) and os.path.exists(normalized_path):
        return normalized_path

    project_root = os.path.abspath(
        os.path.join(
            os.path.dirname(__file__),
            ".."
        )
    )
    relative_path = normalized_path.lstrip("/\\")
    file_name = os.path.basename(relative_path)
    candidates = [
        os.path.join(project_root, relative_path),
        os.path.join(project_root, "frontend", relative_path),
        os.path.join(project_root, "backend", relative_path),
        os.path.join(project_root, "backend", "uploads", file_name),
        os.path.join(project_root, "uploads", file_name),
        os.path.join(project_root, "frontend", "matched_employee_photos", file_name),
        os.path.abspath(relative_path)
    ]

    for candidate in candidates:
        if os.path.exists(candidate):
            return candidate

    return None


def safe_json_response(response):
    """Return parsed backend JSON or a safe error payload for non-JSON replies."""

    try:
        return response.json()
    except ValueError:
        return {
            "status": "error",
            "message": response.text or "Backend returned a non-JSON response"
        }


def post_request(url, data=None, files=None, json_body=None, timeout=180):
    """POST to the backend and normalize connection/JSON errors."""

    try:
        response = requests.post(
            url,
            data=data,
            files=files,
            json=json_body,
            timeout=timeout
        )
        return response, safe_json_response(response)
    except requests.RequestException as error:
        return None, {
            "status": "error",
            "message": f"Backend connection failed: {error}"
        }


def get_request(url, params=None):
    """GET from the backend and normalize connection/JSON errors."""

    try:
        response = requests.get(
            url,
            params=params,
            timeout=60
        )
        return response, safe_json_response(response)
    except requests.RequestException as error:
        return None, {
            "status": "error",
            "message": f"Backend connection failed: {error}"
        }


def render_person(person, title="Identity Profile"):
    """Display one identity record with photo and important fields."""

    if not person:
        return

    st.markdown(f'<div class="section-title">{title}</div>', unsafe_allow_html=True)

    image_col, detail_col = st.columns([1, 4], gap="large")
    with image_col:
        photo_path = resolve_photo_path(person.get("photo_path"))
        if photo_path and os.path.exists(photo_path):
            st.image(photo_path, width=170)
        else:
            st.warning("Photo not available")

    with detail_col:
        st.markdown(
            f"""
            <div class="profile-name">{person.get('full_name') or '-'}</div>
            <div class="profile-id">Employee ID: {person.get('employee_id') or '-'}</div>
            <div class="kv-grid">
                <div><div class="kv-label">DOB</div><div class="kv-value">{person.get('date_of_birth') or '-'}</div></div>
                <div><div class="kv-label">Department</div><div class="kv-value">{person.get('department') or '-'}</div></div>
                <div><div class="kv-label">Aadhaar</div><div class="kv-value">{person.get('aadhar_number') or '-'}</div></div>
                <div><div class="kv-label">PAN</div><div class="kv-value">{person.get('pan_number') or '-'}</div></div>
                <div><div class="kv-label">Voter ID</div><div class="kv-value">{person.get('voter_id_number') or '-'}</div></div>
                <div><div class="kv-label">Driving Licence</div><div class="kv-value">{person.get('driving_license_number') or '-'}</div></div>
                <div><div class="kv-label">Passport</div><div class="kv-value">{person.get('passport_number') or '-'}</div></div>
                <div><div class="kv-label">Phone</div><div class="kv-value">{person.get('phone_number') or '-'}</div></div>
                <div><div class="kv-label">Email</div><div class="kv-value">{person.get('email') or '-'}</div></div>
                <div><div class="kv-label">State</div><div class="kv-value">{person.get('state') or '-'}</div></div>
            </div>
            """,
            unsafe_allow_html=True
        )


def render_face_evidence(left_label, left_path, right_label, right_path):
    """Show document/uploaded face evidence beside database face evidence."""

    left, right = st.columns(2, gap="large")

    with left:
        st.markdown(f'<div class="evidence-label">{left_label}</div>', unsafe_allow_html=True)
        resolved_left_path = resolve_photo_path(left_path)

        if resolved_left_path:
            st.image(resolved_left_path, width=210)
        else:
            st.warning("Image not available")

    with right:
        st.markdown(f'<div class="evidence-label">{right_label}</div>', unsafe_allow_html=True)
        resolved_right_path = resolve_photo_path(right_path)

        if resolved_right_path:
            st.image(resolved_right_path, width=210)
        else:
            st.warning("Image not available")


def render_persistent_upload_preview(
    uploaded_file,
    saved_path,
    waiting_message,
    width
):
    """Show the live uploaded file, then fall back to the saved job file path."""

    if uploaded_file is not None:
        st.image(uploaded_file, width=width)
        return

    resolved_path = resolve_photo_path(saved_path)

    if resolved_path:
        st.image(resolved_path, width=width)
        return

    status_panel(waiting_message, "neutral")


def render_decision(decision, face_verification):
    """Show the final verification decision and face score metadata."""

    decision_status = (decision or {}).get("status")
    decision_message = (decision or {}).get("message", "Decision unavailable")

    if decision_status == "VERIFIED":
        status_panel(decision_message, "success")
    elif decision_status == "MANUAL REVIEW":
        status_panel(decision_message, "warning")
    elif decision_status == "NOT VERIFIED":
        status_panel(decision_message, "danger")
    else:
        status_panel(decision_message, "neutral")

    if face_verification:
        score = face_verification.get("score")
        threshold = face_verification.get("threshold")
        method = face_verification.get("method")
        st.caption(f"Face method: {method or '-'} | Score: {score if score is not None else '-'} | Threshold: {threshold if threshold is not None else '-'}")


def render_risk_assessment(risk_assessment):
    """Render risk score, check breakdown, passed checks, and risk flags."""

    if not risk_assessment:
        return

    risk_score = risk_assessment.get("risk_score", 0)
    risk_level = risk_assessment.get("risk_level", "UNKNOWN")
    risk_decision = risk_assessment.get("decision", "UNKNOWN")
    chip_class = {
        "LOW": "risk-low",
        "MEDIUM": "risk-medium",
        "HIGH": "risk-high"
    }.get(risk_level, "risk-medium")

    score_col, checks_col, evidence_col = st.columns([0.8, 1.2, 1.5], gap="large")

    with score_col:
        st.markdown(
            f"""
            <div class="risk-card">
                <div class="risk-score">{risk_score}/100</div>
                <div class="risk-meta">Automation Risk Score</div>
                <div class="risk-chip {chip_class}">{risk_level} RISK</div>
                <div class="risk-meta">Decision: {risk_decision}</div>
            </div>
            """,
            unsafe_allow_html=True
        )

    with checks_col:
        checks = risk_assessment.get("checks") or {}
        st.markdown('<div class="evidence-label">Score Breakdown</div>', unsafe_allow_html=True)
        for label, value in {
            "Document Number": checks.get("document_number", 0),
            "Date Of Birth": checks.get("date_of_birth", 0),
            "Name Match": checks.get("name", 0),
            "Face Match": checks.get("face", 0),
            "Document Format": checks.get("document_format", 0)
        }.items():
            st.caption(f"{label}: {value} points")
            st.progress(min(value / 35, 1.0) if label == "Document Number" else min(value / 20, 1.0))

    with evidence_col:
        reasons = risk_assessment.get("reasons") or []
        flags = risk_assessment.get("flags") or []

        st.markdown('<div class="evidence-label">Passed Checks</div>', unsafe_allow_html=True)
        if reasons:
            for reason in reasons:
                st.success(reason)
        else:
            st.info("No positive checks were confirmed.")

        st.markdown('<div class="evidence-label">Risk Flags</div>', unsafe_allow_html=True)
        if flags:
            for flag in flags:
                st.warning(flag)
        else:
            st.success("No risk flags detected.")


def render_review_case(review_case):
    """Render one manual review case and allow approve/reject submission."""

    case_id = review_case.get("id")
    case_status = review_case.get("status")
    decision = review_case.get("decision") or {}
    face_result = review_case.get("face_result") or {}
    database_match = review_case.get("database_match")
    extracted_data = review_case.get("extracted_data") or {}
    risk_assessment = decision.get("risk_assessment")

    st.markdown(
        f"""
        <div class="panel">
            <div class="profile-name">Review Case #{case_id}</div>
            <div class="profile-id">
                Status: {case_status} | Document: {review_case.get('document_type') or '-'} |
                Created: {review_case.get('created_at') or '-'}
            </div>
            <div class="caption-text">{decision.get('message') or 'Manual review required.'}</div>
        </div>
        """,
        unsafe_allow_html=True
    )

    render_decision(decision, face_result)
    render_risk_assessment(risk_assessment)

    if database_match:
        render_person(database_match, "Database Record For Review")

    approve_col, update_col = st.columns([1, 1.4], gap="large")

    with approve_col:
        approve_clicked = st.button(
            "Approve Case",
            type="primary",
            use_container_width=True,
            key=f"approve_case_{case_id}"
        )

    if approve_clicked:
        response, result = post_request(
            f"{MANUAL_REVIEW_URL}/{case_id}/decision",
            data={
                "reviewer_decision": "APPROVED",
                "reviewer_notes": ""
            }
        )

        if response is None or response.status_code != 200:
            status_panel(result.get("message", "Manual review approval failed."), "danger")
        else:
            st.session_state["manual_review_success_message"] = (
                f"Verification is successful for review case #{case_id}."
            )
            st.rerun()

    with update_col:
        employee_id = (database_match or {}).get("employee_id") or review_case.get("employee_id")

        if not employee_id or not database_match:
            status_panel("Update is unavailable because no matched database identity was found.", "warning")
        else:
            field_labels = [
                label
                for label, _ in REVIEW_UPDATE_FIELDS
            ]
            selected_update_fields = st.multiselect(
                "Fields to update",
                field_labels,
                key=f"review_update_fields_{case_id}"
            )
            update_payload = dict(database_match)

            for label, field_name in REVIEW_UPDATE_FIELDS:
                if label not in selected_update_fields:
                    continue

                suggested_value = extracted_data.get(field_name)
                current_value = database_match.get(field_name)
                update_payload[field_name] = st.text_input(
                    label,
                    value=str(suggested_value or current_value or ""),
                    key=f"review_update_{case_id}_{field_name}"
                )

            update_clicked = st.button(
                "Update Case",
                use_container_width=True,
                disabled=not selected_update_fields,
                key=f"update_case_{case_id}"
            )

            if update_clicked:
                update_data = {
                    field_name: update_payload.get(field_name) or ""
                    for _, field_name in REVIEW_UPDATE_FIELDS
                }

                if not str(update_data.get("full_name") or "").strip():
                    status_panel("Full name is required before updating the identity.", "danger")
                    return

                update_response, update_result = post_request(
                    f"{ADMIN_IDENTITIES_URL}/{employee_id}/update",
                    data=update_data
                )

                if update_response is None or update_response.status_code != 200:
                    status_panel(update_result.get("message", "Identity update failed."), "danger")
                    return

                decision_response, decision_result = post_request(
                    f"{MANUAL_REVIEW_URL}/{case_id}/decision",
                    data={
                        "reviewer_decision": "APPROVED",
                        "reviewer_notes": "Identity updated from manual review."
                    }
                )

                if decision_response is None or decision_response.status_code != 200:
                    status_panel(decision_result.get("message", "Identity updated, but review case approval failed."), "danger")
                    return

                st.session_state["manual_review_success_message"] = (
                    f"Verification is successful. Identity {employee_id} was updated from review case #{case_id}."
                )
                st.rerun()


def uploaded_file_payload(field_name, uploaded_file):
    """Convert a Streamlit uploaded file into the `requests` files format."""

    return {
        field_name: (
            uploaded_file.name,
            uploaded_file.getvalue(),
            uploaded_file.type
        )
    }


def apply_admin_create_ocr_prefill(extracted_data):
    """Fill create-identity form fields from OCR output when values are present."""

    prefill_mapping = {
        "admin_create_full_name": ("Full Name", extracted_data.get("full_name"), False),
        "admin_create_dob": ("Date of Birth", extracted_data.get("date_of_birth"), False),
        "admin_create_aadhaar": ("Aadhaar Number", extracted_data.get("aadhar_number"), True),
        "admin_create_pan": ("PAN Number", extracted_data.get("pan_number"), True),
        "admin_create_voter": ("Voter ID Number", extracted_data.get("voter_id_number"), True),
        "admin_create_dl": ("Driving Licence Number", extracted_data.get("driving_license_number"), True),
        "admin_create_passport": ("Passport Number", extracted_data.get("passport_number"), True)
    }
    changed_fields = []

    for key, (label, value, overwrite_existing) in prefill_mapping.items():
        if not value:
            continue

        normalized_value = str(value).strip()
        if not normalized_value:
            continue

        if not overwrite_existing and st.session_state.get(key):
            continue

        st.session_state[key] = normalized_value
        changed_fields.append(label)

    return changed_fields


def flatten_osint_match_results(result_rows):
    """Flatten OSINT result rows that contain nested `matches` arrays."""

    flattened_rows = []

    for result_row in result_rows or []:
        matches = result_row.get("matches") or []

        if not matches:
            flattened_rows.append(
                {
                    "target": result_row.get("target"),
                    "input_type": result_row.get("input_type"),
                    "result_status": result_row.get("status"),
                    "platform": "-",
                    "match_status": result_row.get("message") or "-",
                    "category": "-",
                    "details": result_row.get("message") or "-"
                }
            )
            continue

        for match in matches:
            flattened_rows.append(
                {
                    "target": result_row.get("target"),
                    "input_type": result_row.get("input_type"),
                    "result_status": result_row.get("status"),
                    "platform": match.get("platform"),
                    "match_status": match.get("status") or result_row.get("status"),
                    "category": match.get("category"),
                    "details": match.get("details") or match.get("message")
                }
            )

    return flattened_rows


def humanize_payload_key(key):
    """Convert provider payload keys into readable dashboard labels."""

    return str(key or "").replace("_", " ").strip().title()


def collect_osint_urls(value, source="Result"):
    """Recursively collect URL-like fields from arbitrary OSINT payloads."""

    collected_urls = []

    if isinstance(value, dict):
        for key, nested_value in value.items():
            nested_source = f"{source} / {humanize_payload_key(key)}"

            if (
                isinstance(nested_value, str)
                and nested_value.startswith(("http://", "https://"))
            ):
                collected_urls.append(
                    {
                        "source": nested_source,
                        "url": nested_value
                    }
                )

            collected_urls.extend(
                collect_osint_urls(
                    nested_value,
                    nested_source
                )
            )

    elif isinstance(value, list):
        for index, nested_value in enumerate(value, 1):
            collected_urls.extend(
                collect_osint_urls(
                    nested_value,
                    f"{source} #{index}"
                )
            )

    return collected_urls


def flatten_payload_for_display(value, prefix=""):
    """Flatten arbitrary OSINT payloads into key/value rows for detailed display."""

    rows = []

    if isinstance(value, dict):
        for key, nested_value in value.items():
            next_prefix = (
                f"{prefix}.{key}"
                if prefix
                else str(key)
            )
            rows.extend(
                flatten_payload_for_display(
                    nested_value,
                    next_prefix
                )
            )

        return rows

    if isinstance(value, list):
        if not value:
            rows.append(
                {
                    "field": prefix or "items",
                    "value": "-"
                }
            )
            return rows

        for index, nested_value in enumerate(value, 1):
            rows.extend(
                flatten_payload_for_display(
                    nested_value,
                    f"{prefix}[{index}]"
                )
            )

        return rows

    rows.append(
        {
            "field": prefix or "value",
            "value": value
        }
    )

    return rows


def dynamic_osint_columns(rows):
    """Build readable table columns from arbitrary OSINT dictionaries."""

    priority_keys = [
        "target",
        "target_username",
        "input_type",
        "platform",
        "status",
        "profile_url",
        "url",
        "name",
        "username",
        "message",
        "details"
    ]
    discovered_keys = []

    for row in rows or []:
        if not isinstance(row, dict):
            continue

        for key in row.keys():
            if key not in discovered_keys:
                discovered_keys.append(key)

    ordered_keys = [
        key
        for key in priority_keys
        if key in discovered_keys
    ]
    ordered_keys.extend(
        key
        for key in discovered_keys
        if key not in ordered_keys
    )

    return [
        (
            humanize_payload_key(key),
            key
        )
        for key in ordered_keys[:10]
    ]


def render_generic_osint_section(section_key, section_value):
    """Render unknown OSINT provider sections such as Facebook automatically."""

    title = humanize_payload_key(section_key)
    st.markdown(f"**{title}**")

    if isinstance(section_value, list):
        if all(isinstance(item, dict) for item in section_value):
            render_light_table(
                section_value,
                dynamic_osint_columns(section_value),
                f"No {title.lower()} were returned."
            )
            with st.expander(f"{title} Detailed Fields"):
                render_light_table(
                    flatten_payload_for_display(section_value, section_key),
                    [
                        ("Field", "field"),
                        ("Value", "value")
                    ],
                    f"No {title.lower()} details were returned."
                )
        else:
            render_light_table(
                [
                    {
                        "value": item
                    }
                    for item in section_value
                ],
                [
                    ("Value", "value")
                ],
                f"No {title.lower()} were returned."
            )
        return

    if isinstance(section_value, dict):
        render_light_table(
            [section_value],
            dynamic_osint_columns([section_value]),
            f"No {title.lower()} details were returned."
        )
        with st.expander(f"{title} Detailed Fields"):
            render_light_table(
                flatten_payload_for_display(section_value, section_key),
                [
                    ("Field", "field"),
                    ("Value", "value")
                ],
                f"No {title.lower()} details were returned."
            )
        return

    render_light_table(
        [
            {
                "field": title,
                "value": section_value
            }
        ],
        [
            ("Field", "field"),
            ("Value", "value")
        ],
        f"No {title.lower()} value was returned."
    )


def first_non_empty(*values):
    """Return the first meaningful value from a list of candidates."""

    for value in values:
        if value not in (None, "", [], {}):
            return value

    return None


def key_has_any_token(key, tokens):
    """Check whether a payload key contains any matching token."""

    normalized_key = str(key or "").lower()

    return any(token in normalized_key for token in tokens)


def find_nested_url(value, key_tokens, excluded_key_tokens=None):
    """Find the first valid URL stored under keys that match token hints."""

    excluded_key_tokens = excluded_key_tokens or []

    if isinstance(value, dict):
        for key, nested_value in value.items():
            if key_has_any_token(key, excluded_key_tokens):
                continue

            if (
                key_has_any_token(key, key_tokens)
                and isinstance(nested_value, str)
                and nested_value.startswith(("http://", "https://"))
                and not is_base64_like_value(nested_value)
            ):
                return nested_value

        for key, nested_value in value.items():
            if key_has_any_token(key, excluded_key_tokens):
                continue

            found_url = find_nested_url(
                nested_value,
                key_tokens,
                excluded_key_tokens
            )

            if found_url:
                return found_url

    if isinstance(value, list):
        for nested_value in value:
            found_url = find_nested_url(
                nested_value,
                key_tokens,
                excluded_key_tokens
            )

            if found_url:
                return found_url

    return None


def extract_profile_url(row):
    """Extract the most likely public profile URL from an OSINT row."""

    return first_non_empty(
        row.get("profile_url"),
        row.get("profileUrl"),
        row.get("url"),
        row.get("link"),
        find_nested_url(
            row,
            ["profile", "url", "link"],
            ["avatar", "image", "photo", "base64"]
        )
    )


def extract_avatar_url(row):
    """Extract the most likely avatar/photo URL from an OSINT row."""

    return first_non_empty(
        row.get("avatar_url"),
        row.get("avatarUrl"),
        row.get("image_url"),
        row.get("photo_url"),
        find_nested_url(
            row,
            ["avatar", "image", "photo", "picture"],
            ["base64"]
        )
    )


def should_hide_extracted_field(key, value):
    """Decide which OSINT fields should move to columns or stay hidden."""

    if is_base64_like_value(value):
        return True

    normalized_key = str(key or "").lower()
    hidden_tokens = [
        "base64",
        "avatar_url",
        "avatarurl",
        "profile_url",
        "profileurl",
        "image_url",
        "photo_url",
        "url",
        "link"
    ]

    return any(token in normalized_key for token in hidden_tokens)


def is_phone_or_email_platform(platform):
    """Return True when an enriched row is actually phone/email intelligence."""

    normalized_platform = str(platform or "").lower()
    phone_email_tokens = [
        "phone",
        "phonenumber",
        "phonenumbers",
        "network",
        "carrier",
        "telecom",
        "email",
        "gmail",
        "zerobounce",
        "domain"
    ]

    return any(token in normalized_platform for token in phone_email_tokens)


def readable_payload_text(value):
    """Convert nested OSINT values into readable text instead of JSON."""

    if value is None or value == "":
        return "-"

    if is_base64_like_value(value):
        return "[hidden base64 data]"

    if isinstance(value, dict):
        lines = []

        for key, nested_value in value.items():
            if nested_value in (None, "", [], {}):
                continue

            if should_hide_extracted_field(key, nested_value):
                continue

            lines.append(
                f"{humanize_payload_key(key)}: {readable_payload_text(nested_value)}"
            )

        return "\n".join(lines) if lines else "-"

    if isinstance(value, list):
        if not value:
            return "-"

        rendered_items = [
            readable_payload_text(item)
            for item in value
            if item not in (None, "", [], {})
        ]

        return "\n".join(
            f"{index}. {item}"
            for index, item in enumerate(rendered_items, 1)
        ) if rendered_items else "-"

    return str(value)


def flatten_social_media_results(results):
    """Combine username, Instagram, Facebook, and future social results."""

    social_rows = []
    excluded_keys = {
        "inputs_processed",
        "phone_results",
        "email_results",
        "all_matches",
        "profile_url",
        "risk_notes"
    }

    for row in results.get("username_results") or []:
        matches = row.get("matches") or []

        if matches:
            for match in matches:
                if not isinstance(match, dict):
                    continue

                enriched_data = match.get("enriched_data") or {}
                social_rows.append(
                    {
                        "source": "Username Search",
                        "target": row.get("target"),
                        "platform": match.get("platform") or row.get("platform"),
                        "status": match.get("status") or row.get("status"),
                        "profile_url": extract_profile_url(match),
                        "avatar_url": extract_avatar_url(match),
                        "bio": enriched_data.get("bio"),
                        "extracted_text": readable_payload_text(
                            enriched_data
                            or match.get("details")
                            or match.get("message")
                        )
                    }
                )
            continue

        social_rows.append(
            {
                "source": "Username Search",
                "target": row.get("target"),
                "platform": row.get("platform"),
                "status": row.get("status"),
                "profile_url": extract_profile_url(row),
                "avatar_url": extract_avatar_url(row),
                "bio": row.get("bio"),
                "extracted_text": readable_payload_text(
                    row.get("extracted_data")
                    or row.get("details")
                    or row.get("message")
                )
            }
        )

    for row in results.get("instagram_results") or []:
        extracted_data = row.get("extracted_data") or {}
        social_rows.append(
            {
                "source": "Instagram",
                "target": row.get("target_username") or row.get("target"),
                "platform": row.get("platform") or "Instagram",
                "status": row.get("status"),
                "profile_url": extract_profile_url(row),
                "avatar_url": extract_avatar_url(row),
                "extracted_text": readable_payload_text(extracted_data)
            }
        )

    for section_key, section_value in results.items():
        if section_key in excluded_keys or section_key in {
            "username_results",
            "instagram_results"
        }:
            continue

        if not section_key.endswith("_results"):
            continue

        section_rows = section_value if isinstance(section_value, list) else [section_value]

        for row in section_rows:
            if not isinstance(row, dict):
                continue

            social_rows.append(
                {
                    "source": humanize_payload_key(section_key),
                    "target": (
                        row.get("target")
                        or row.get("target_username")
                        or row.get("username")
                    ),
                    "platform": row.get("platform") or humanize_payload_key(section_key),
                    "status": row.get("status"),
                    "profile_url": extract_profile_url(row),
                    "avatar_url": extract_avatar_url(row),
                    "extracted_text": readable_payload_text(
                        row.get("extracted_data")
                        or row.get("details")
                        or row
                    )
                }
            )

    if results.get("profile_url"):
        social_rows.insert(
            0,
            {
                "source": "Profile URL",
                "target": "-",
                "platform": "OSINT",
                "status": "found",
                "profile_url": results.get("profile_url"),
                "avatar_url": extract_avatar_url(results),
                "extracted_text": "-"
            }
        )

    return social_rows


def render_osint_results(results, normalized=None):
    """Render OSINT provider results in the requested focused order."""

    results = results or {}
    normalized = normalized or {}
    phone_results = results.get("phone_results") or []
    email_results = results.get("email_results") or []
    social_media_results = normalized.get("profiles") or flatten_social_media_results(results)
    normalized_contacts = normalized.get("contacts") or []
    normalized_phone_results = [
        contact
        for contact in normalized_contacts
        if contact.get("contact_type") == "phone"
    ]
    normalized_email_results = [
        contact
        for contact in normalized_contacts
        if contact.get("contact_type") == "email"
    ]

    metric_one, metric_two, metric_three = st.columns(3)
    metric_one.metric("Social Media", len(social_media_results))
    metric_two.metric("Phone Results", len(normalized_phone_results or phone_results))
    metric_three.metric("Email Results", len(normalized_email_results or email_results))

    st.markdown("**Social Media Results**")
    render_light_table(
        social_media_results,
        [
            ("Target", "target"),
            ("Platform", "platform"),
            ("Avatar Image", avatar_image_value),
            ("Bio / Extracted Text", lambda row: readable_payload_text(row.get("bio") or row.get("extracted_text"))),
            ("Profile URL", "profile_url"),
            ("Avatar URL", "avatar_url")
        ],
        "No social media results were returned."
    )

    st.markdown("**Phone Results**")
    render_light_table(
        normalized_phone_results or flatten_osint_match_results(phone_results),
        [
            ("Target", "target"),
            ("Input Type", lambda row: row.get("contact_type") or row.get("input_type")),
            ("Result Status", lambda row: row.get("status") or row.get("result_status")),
            ("Platform", "platform"),
            ("Details", lambda row: readable_payload_text(row.get("details")))
        ],
        "No phone results were returned."
    )

    st.markdown("**Email Results**")
    render_light_table(
        normalized_email_results or flatten_osint_match_results(email_results),
        [
            ("Target", "target"),
            ("Input Type", lambda row: row.get("contact_type") or row.get("input_type")),
            ("Result Status", lambda row: row.get("status") or row.get("result_status")),
            ("Platform", "platform"),
            ("Details", lambda row: readable_payload_text(row.get("details")))
        ],
        "No email results were returned."
    )


def dedupe_osint_avatar_candidates(candidates):
    """Remove duplicate OSINT avatar candidates while keeping useful metadata."""

    deduped = []
    seen = set()

    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue

        if not avatar_row_has_usable_image(candidate):
            continue

        profile_identity = str(
            candidate.get("profile_url")
            or candidate.get("url")
            or ""
        ).strip().lower().rstrip("/")
        avatar_identity = str(
            candidate.get("avatar_url")
            or candidate.get("avatar_path")
            or ""
        ).strip().lower()

        if profile_identity:
            key = ("profile_url", profile_identity)
        elif avatar_identity:
            key = ("avatar", avatar_identity)
        else:
            key = (
                "metadata",
                str(candidate.get("platform") or "").lower(),
                str(candidate.get("target") or "").lower(),
                str(candidate.get("bio") or candidate.get("extracted_text") or "").lower()
            )

        if key in seen:
            continue

        seen.add(key)
        deduped.append(candidate)

    return deduped


def build_osint_avatar_candidates(job):
    """Build avatar candidates from normalized rows and raw OSINT fallback data."""

    job = job or {}
    normalized = job.get("normalized") or {}
    results = job.get("results") or {}
    candidates = []

    for section_key, source_label in (
        ("profiles", "Social Profile"),
        ("matches", "Enriched Match")
    ):
        for row in normalized.get(section_key) or []:
            if not isinstance(row, dict):
                continue

            candidate = dict(row)
            candidate["source"] = candidate.get("source") or source_label

            if not candidate.get("profile_url") and candidate.get("url"):
                candidate["profile_url"] = candidate.get("url")

            candidates.append(candidate)

    if results:
        for row in flatten_social_media_results(results):
            candidate = dict(row)
            candidate["source"] = candidate.get("source") or "Raw Social Result"
            candidates.append(candidate)

        for row in results.get("all_matches") or []:
            if not isinstance(row, dict):
                continue

            if is_phone_or_email_platform(row.get("platform")):
                continue

            candidate = dict(row)
            candidate["source"] = candidate.get("source") or "Raw Enriched Match"
            candidate["profile_url"] = candidate.get("profile_url") or candidate.get("url")
            candidate["avatar_url"] = candidate.get("avatar_url") or extract_avatar_url(
                candidate.get("enriched_data") or candidate
            )
            candidate["bio"] = candidate.get("bio") or nested_value(candidate, "enriched_data.bio")
            candidates.append(candidate)

    return dedupe_osint_avatar_candidates(candidates)


def render_osint_avatar_verification(job):
    """Verify OSINT avatars against DB faces and render final profile summary."""

    job_id = (job or {}).get("job_id")

    if not job_id:
        return

    avatar_profiles = build_osint_avatar_candidates(job)

    st.markdown("**OSINT Images For Verification**")

    if not avatar_profiles:
        status_panel(
            (
                "No OSINT avatar images are available for face verification. "
                "The job may contain profile text only, or the provider did not send "
                "a usable avatar_url/avatar_base64 field."
            ),
            "warning"
        )
        return

    status_panel(
        "Review the OSINT avatar images below. Approve only the images you want to compare with registered database faces.",
        "neutral"
    )

    selected_profiles = []

    for start_index in range(0, len(avatar_profiles), 3):
        row_columns = st.columns(3, gap="large")

        for offset, profile in enumerate(avatar_profiles[start_index:start_index + 3]):
            profile_index = start_index + offset
            checkbox_key = f"osint_avatar_select_{job_id}_{profile_index}"

            with row_columns[offset]:
                st.markdown(
                    f"""
                        <div class="news-card">
                            <div class="news-card-title">{html.escape(str(profile.get("platform") or "Unknown Platform"))}</div>
                            <div class="news-card-meta">Source: {html.escape(str(profile.get("source") or "-"))}</div>
                            <div class="news-card-meta">Target: {html.escape(str(profile.get("target") or "-"))}</div>
                            <div style="margin:10px 0;">{formatted_table_cell(avatar_image_value(profile))}</div>
                            <div class="news-card-meta">Status: {html.escape(str(profile.get("status") or "-"))}</div>
                    </div>
                    """,
                    unsafe_allow_html=True
                )

                if profile.get("profile_url"):
                    st.markdown(f"[Open profile]({profile.get('profile_url')})")

                approved = st.checkbox(
                    "Approve for face search",
                    value=True,
                    key=checkbox_key
                )

                if approved:
                    selected_profiles.append(profile)

    verify_clicked = st.button(
        "Verify Approved OSINT Avatars With Database Faces",
        key=f"verify_osint_avatars_{job_id}",
        type="primary",
        use_container_width=True
    )

    result_key = f"osint_avatar_verification_{job_id}"

    if verify_clicked:
        if not selected_profiles:
            status_panel("Select at least one OSINT avatar image before verification.", "danger")
            return

        with st.spinner("Comparing OSINT avatar images with database faces..."):
            response, result = post_request(
                f"{OSINT_AVATAR_VERIFY_URL}/{job_id}/verify-avatars",
                json_body={
                    "approved_avatars": selected_profiles
                },
                timeout=900
            )

        if response is None or response.status_code != 200:
            status_panel(result.get("message", "OSINT avatar verification failed."), "danger")
            return

        st.session_state[result_key] = result

    verification_result = st.session_state.get(result_key)

    if not verification_result:
        return

    st.markdown("**Investigation Result**")
    conclusion = verification_result.get("conclusion") or {}
    decision = conclusion.get("decision")
    summary = conclusion.get("summary") or "Verification summary unavailable."

    if decision == "VERIFIED":
        status_panel(summary, "success")
    elif decision == "NO AVATAR":
        status_panel(summary, "warning")
    else:
        status_panel(summary, "danger")

    verified_identity = verification_result.get("verified_identity")
    verification_rows = verification_result.get("avatar_verifications") or []
    matched_rows = [
        row
        for row in verification_rows
        if row.get("matched")
    ]

    metric_one, metric_two, metric_three = st.columns(3)
    metric_one.metric("Approved Avatars Checked", len(verification_rows))
    metric_two.metric("Face Matches", len(matched_rows))
    metric_three.metric("Decision", decision or "-")

    if verified_identity:
        render_person(
            verified_identity,
            "Final Verified Profile Summary"
        )

        matched_platforms = ", ".join(
            str(row.get("platform") or "-")
            for row in matched_rows
        )
        status_panel(
            f"Investigative conclusion: OSINT avatar evidence from {matched_platforms or 'selected profiles'} matched the registered database identity.",
            "success"
        )

    st.markdown("**Avatar Match Evidence**")
    render_light_table(
        verification_rows,
        [
            ("Platform", "platform"),
            ("Target", "target"),
            ("OSINT Avatar", avatar_image_value),
            ("Profile URL", "profile_url"),
            ("Matched", "matched"),
            ("DB Employee ID", lambda row: (row.get("database_match") or {}).get("employee_id")),
            ("DB Name", lambda row: (row.get("database_match") or {}).get("full_name")),
            ("Message", "message")
        ],
        "No avatar verification evidence was returned."
    )


OSINT_TERMINAL_STATUSES = {"COMPLETED", "FAILED"}
FACE_SEARCH_TERMINAL_STATUSES = {"COMPLETED", "FAILED"}
DOCUMENT_VALIDATION_TERMINAL_STATUSES = {"COMPLETED", "FAILED"}


def normalize_osint_status(status):
    """Normalize provider-specific OSINT statuses into dashboard states."""

    normalized_status = str(status or "UNKNOWN").strip().upper()

    if normalized_status == "QUEUED":
        return "PENDING"

    if normalized_status in {"SUCCESS", "SUCCEEDED", "DONE"}:
        return "COMPLETED"

    if normalized_status in {"ERROR", "FAILURE"}:
        return "FAILED"

    return normalized_status


def render_osint_job_card(job):
    """Render OSINT job status and final results for active or completed jobs."""

    job = dict(job or {})
    status = normalize_osint_status(job.get("status"))
    job["status"] = status

    status_class = {
        "PENDING": "status-chip-pending",
        "PROCESSING": "status-chip-processing",
        "COMPLETED": "status-chip-completed",
        "FAILED": "status-chip-failed"
    }.get(status, "status-chip-processing")

    st.markdown(
        f"""
        <div class="profile-id">
            Job ID: {html.escape(str(job.get("job_id") or "-"))}
            <span class="status-chip {status_class}">{html.escape(status)}</span>
        </div>
        """,
        unsafe_allow_html=True
    )

    if status == "PENDING":
        status_panel("OSINT job is pending and waiting for provider submission.", "neutral")
    elif status == "PROCESSING":
        status_panel("OSINT provider is processing the search in the background.", "neutral")
    elif status == "COMPLETED":
        status_panel("OSINT search completed and the result was stored.", "success")
        render_osint_results(
            job.get("results"),
            job.get("normalized")
        )
        render_osint_avatar_verification(job)
    elif status == "FAILED":
        status_panel(
            html.escape(job.get("error_message") or "OSINT search failed."),
            "danger"
        )
    else:
        status_panel(f"OSINT status: {html.escape(status)}", "warning")

    st.caption(
        f"Job ID: {job.get('job_id')} | "
        f"Last update: {job.get('updated_at') or '-'}"
    )

    return status


@st.fragment(run_every="10s")
def render_osint_job_status(job_id):
    """Poll one OSINT job until it reaches a terminal status."""

    st.markdown('<div class="section-title">OSINT Search</div>', unsafe_allow_html=True)
    response, result = get_request(f"{OSINT_JOBS_URL}/{job_id}")

    if response is None or response.status_code != 200:
        status_panel(
            html.escape(result.get("message", "OSINT job status could not be loaded.")),
            "danger"
        )
        return

    job = result.get("job") or {}
    status = render_osint_job_card(job)

    if status in OSINT_TERMINAL_STATUSES:
        st.session_state["last_osint_job"] = job
        st.session_state.pop("active_osint_job_id", None)
        st.rerun(scope="app")


def render_document_validation_result_payload(result_payload):
    """Render a completed document-validation result from a background job."""

    result_payload = result_payload or {}
    decision = result_payload.get("decision", {})
    extracted_data = result_payload.get("extracted_data", {})
    database_match = result_payload.get("database_match")
    face_verification = result_payload.get("face_verification", {})
    risk_assessment = result_payload.get("risk_assessment", {})
    manual_review_case = result_payload.get("manual_review_case")

    render_decision(decision, face_verification)
    render_risk_assessment(risk_assessment)

    if manual_review_case:
        status_panel(
            f"Manual review case #{manual_review_case.get('id')} has been created in the review queue.",
            "warning"
        )

    uploaded_face_path = face_verification.get("uploaded_face_path")
    database_face_path = face_verification.get("database_face_path")
    if uploaded_face_path or database_face_path:
        render_face_evidence(
            "Face Extracted From Uploaded Document",
            uploaded_face_path,
            "Stored Database Face",
            database_face_path
        )

    with st.expander("OCR Raw Text"):
        st.text(extracted_data.get("raw_text", ""))

    if database_match:
        render_person(database_match, "Verified Database Record")


def render_document_validation_job_card(job):
    """Render one background document-validation job state and result."""

    job = job or {}
    status = str(job.get("status") or "PENDING").upper()
    progress_percent = int(job.get("progress_percent") or 0)
    progress_message = job.get("progress_message") or "Preparing document validation."

    st.markdown('<div class="section-title">Document Validation</div>', unsafe_allow_html=True)
    st.progress(
        min(max(progress_percent, 0), 100),
        text=f"{min(max(progress_percent, 0), 100)}% - {progress_message}"
    )

    if status == "PENDING":
        status_panel("Document validation is queued and waiting to start.", "neutral")
    elif status == "PROCESSING":
        status_panel("Document OCR, database verification, and face checks are running.", "neutral")
    elif status == "COMPLETED":
        status_panel("Document validation completed and the result was stored.", "success")
        render_document_validation_result_payload(job.get("result") or {})
    elif status == "FAILED":
        status_panel(
            html.escape(job.get("error_message") or "Document validation failed."),
            "danger"
        )
    else:
        status_panel(f"Document validation status: {html.escape(status)}", "warning")

    st.caption(
        f"Job ID: {job.get('job_id')} | "
        f"Last update: {job.get('updated_at') or '-'}"
    )

    return status


@st.fragment(run_every="10s")
def render_document_validation_job_status(job_id):
    """Poll one document-validation job until it reaches a terminal status."""

    response, result = get_request(f"{DOCUMENT_VALIDATION_JOBS_URL}/{job_id}")

    if response is None or response.status_code != 200:
        status_panel(
            html.escape(result.get("message", "Document validation job status could not be loaded.")),
            "danger"
        )
        return

    job = result.get("job") or {}
    st.session_state["active_document_validation_job"] = job
    status = render_document_validation_job_card(job)

    if status in DOCUMENT_VALIDATION_TERMINAL_STATUSES:
        st.session_state["last_document_validation_job"] = job
        st.session_state.pop("active_document_validation_job_id", None)
        st.session_state.pop("active_document_validation_job", None)
        st.rerun(scope="app")

def render_face_search_result_payload(result_payload):
    """Render a completed face-search result using the existing evidence widgets."""

    result_payload = result_payload or {}
    database_match = result_payload.get("database_match")
    face_verification = result_payload.get("face_verification", {})

    if result_payload.get("matched") and database_match:
        status_panel(
            "Yes, the uploaded face matched a database user. Details are shared below.",
            "success"
        )
    else:
        status_panel("No confident face match was found in the database.", "danger")

    render_face_evidence(
        "Uploaded Face Image",
        face_verification.get("uploaded_face_path"),
        "Best Database Candidate",
        face_verification.get("database_face_path")
    )

    if face_verification.get("error"):
        st.caption(face_verification.get("error"))

    if database_match:
        render_person(database_match, "Matched User Details")


def render_face_search_job_card(job):
    """Render the current state of one background face-search job."""

    job = job or {}
    status = str(job.get("status") or "PENDING").upper()
    progress_percent = int(job.get("progress_percent") or 0)
    progress_message = job.get("progress_message") or "Preparing face search."

    st.markdown('<div class="section-title">Face Search</div>', unsafe_allow_html=True)
    st.progress(
        min(max(progress_percent, 0), 100),
        text=f"{min(max(progress_percent, 0), 100)}% - {progress_message}"
    )

    if status == "PENDING":
        status_panel("Face search is queued and waiting to start.", "neutral")
    elif status == "PROCESSING":
        total_candidates = job.get("total_candidates")
        message = "Face search is running."
        if total_candidates:
            message += f" Comparing against {total_candidates} database photos."
        status_panel(message, "neutral")
    elif status == "COMPLETED":
        render_face_search_result_payload(job.get("result") or {})
    elif status == "FAILED":
        status_panel(
            html.escape(job.get("error_message") or "Face search failed."),
            "danger"
        )
    else:
        status_panel(f"Face search status: {html.escape(status)}", "warning")

    st.caption(
        f"Job ID: {job.get('job_id')} | "
        f"Last update: {job.get('updated_at') or '-'}"
    )

    return status


@st.fragment(run_every="10s")
def render_face_search_job_status(job_id):
    """Poll one face-search job until it reaches a terminal status."""

    response, result = get_request(f"{FACE_SEARCH_JOBS_URL}/{job_id}")

    if response is None or response.status_code != 200:
        status_panel(
            html.escape(result.get("message", "Face search job status could not be loaded.")),
            "danger"
        )
        return

    job = result.get("job") or {}
    st.session_state["active_face_search_job"] = job
    status = render_face_search_job_card(job)

    if status in FACE_SEARCH_TERMINAL_STATUSES:
        st.session_state["last_face_search_job"] = job
        st.session_state.pop("active_face_search_job_id", None)
        st.session_state.pop("active_face_search_job", None)
        st.rerun(scope="app")


def render_identity_search_results(search_result):
    """Render database identity search results as a paginated table."""

    search_result = search_result or {}
    results = search_result.get("results") or []
    total_matches = search_result.get("total_matches", len(results))

    st.metric("Matches Found", total_matches)

    if not results:
        status_panel("No matching identity record was found.", "warning")
        return

    page_number_key = "identity_search_page_number"
    page_size = 5
    total_pages = max(
        1,
        (len(results) + page_size - 1) // page_size
    )
    current_page = min(
        max(
            1,
            int(st.session_state.get(page_number_key, 1))
        ),
        total_pages
    )
    page_options = list(range(1, total_pages + 1))

    if st.session_state.get("identity_search_page_select") not in page_options:
        st.session_state["identity_search_page_select"] = current_page

    selected_page = st.selectbox(
        "Page",
        page_options,
        index=current_page - 1,
        key="identity_search_page_select"
    )

    if selected_page != current_page:
        st.session_state[page_number_key] = selected_page
        st.rerun()

    start_index = (current_page - 1) * page_size
    end_index = start_index + page_size
    visible_results = results[start_index:end_index]

    st.caption(
        f"Showing {start_index + 1}-{min(end_index, len(results))} of {len(results)} matching records."
    )
    render_light_table(
        visible_results,
        [
            ("Photo", identity_photo_value),
            ("Employee ID", "employee_id"),
            ("Full Name", "full_name"),
            ("DOB", "date_of_birth"),
            ("Aadhaar", "aadhar_number"),
            ("PAN", "pan_number"),
            ("Voter ID", "voter_id_number"),
            ("Driving Licence", "driving_license_number"),
            ("Passport", "passport_number"),
            ("Phone", "phone_number"),
            ("Email", "email"),
            ("Department", "department"),
            ("State", "state"),
            ("Matched Fields", identity_match_reason_text)
        ],
        "No matching identity record was found.",
        table_class="admin-table identity-results-table"
    )


def identity_photo_value(person):
    """Return a large non-cropped identity photo value for table rendering."""

    if not isinstance(person, dict):
        return None

    photo_path = person.get("photo_path")

    if not local_image_path_exists(photo_path):
        return None

    return {
        "image_path": photo_path,
        "image_url": None,
        "image_size": 190,
        "image_fit": "contain"
    }


def identity_match_reason_text(person):
    """Return compact text explaining why an identity row matched."""

    matched_fields = person.get("_matched_fields") or []

    if not matched_fields:
        return "Matched submitted fields"

    lines = []

    for match in matched_fields:
        searched_field = DB_FIELD_LABELS.get(
            match.get("searched_field"),
            str(match.get("searched_field") or "-").replace("_", " ").title()
        )
        matched_column = DB_FIELD_LABELS.get(
            match.get("matched_column"),
            str(match.get("matched_column") or "-").replace("_", " ").title()
        )
        searched_value = str(match.get("searched_value") or "-")
        matched_value = str(match.get("matched_value") or "-")

        lines.append(
            f"{searched_field}: {searched_value} -> {matched_column}: {matched_value}"
        )

    return "\n".join(lines)


def render_identity_match_reason(person):
    """Show which searched field matched before displaying the DB result."""

    matched_fields = person.get("_matched_fields") or []

    if not matched_fields:

        status_panel("This database result matched at least one submitted field.", "neutral")
        return

    match_lines = []

    for match in matched_fields:
        searched_field = DB_FIELD_LABELS.get(
            match.get("searched_field"),
            str(match.get("searched_field") or "-").replace("_", " ").title()
        )
        matched_column = DB_FIELD_LABELS.get(
            match.get("matched_column"),
            str(match.get("matched_column") or "-").replace("_", " ").title()
        )
        searched_value = html.escape(str(match.get("searched_value") or "-"))
        matched_value = html.escape(str(match.get("matched_value") or "-"))

        match_lines.append(
            f"<li>{html.escape(searched_field)} searched as "
            f"<strong>{searched_value}</strong> matched DB "
            f"{html.escape(matched_column)}: <strong>{matched_value}</strong></li>"
        )

    st.markdown(
        f"""
        <div class="status status-success">
            <strong>This database result is shown because:</strong>
            <ul>{''.join(match_lines)}</ul>
        </div>
        """,
        unsafe_allow_html=True
    )


def new_identity_search_row(field="Full Name", value=""):
    """Create a search row with a stable ID for Streamlit widget keys."""

    return {
        "id": uuid.uuid4().hex,
        "field": field,
        "value": value
    }


def ensure_identity_search_row_ids():
    """Add stable IDs to old session rows created before this helper existed."""

    for row in st.session_state.identity_search_rows:
        if not row.get("id"):
            row["id"] = uuid.uuid4().hex


def clear_identity_search_widget_state(row_id):
    """Remove widget state for a deleted search row."""

    st.session_state.pop(f"identity_search_field_{row_id}", None)
    st.session_state.pop(f"identity_search_value_{row_id}", None)
    st.session_state.pop(f"identity_search_face_{row_id}", None)
    st.session_state.pop(f"remove_identity_search_row_{row_id}", None)


def validate_identity_search_rows(search_rows):
    """Validate search rows before database search and OSINT preview creation."""

    criteria = []
    errors = []
    face_image_count = 0

    for index, row in enumerate(search_rows or [], start=1):
        label = row.get("field") or f"Field {index}"
        field = SEARCH_OPTIONS.get(label)
        value = str(row.get("value") or "").strip()

        if field == "face_image":
            face_image_count += 1
        if not value:
            errors.append(f"{label} is blank. Please fill the field or remove it.")
            continue

        if field == "full_name" and not re.fullmatch(r"[A-Za-z]+(?: [A-Za-z]+)*", value):
            errors.append("Full Name should contain only letters and spaces.")

        if field == "email" and not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9._%+-]{0,62}[A-Za-z0-9])?@[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z]{2,})+", value):
            errors.append("Email is not in a proper format.")

        if field == "phone_number":
            if not re.fullmatch(r"\d{10}", value):
                errors.append("Phone number must be exactly 10 digits without country code or special symbols.")

        if field == "username" and not re.fullmatch(r"[A-Za-z0-9@#._]+", value):
            errors.append("Username can contain only letters, numbers, @, #, dot, and underscore.")

        if field:
            criteria.append(
                {
                    "field": field,
                    "value": value
                }
            )

    if face_image_count > 1:
        errors.append("Add only one Face Image field per identity search.")

    return criteria, errors

def build_osint_approval_items(criteria, face_upload=None):
    """Build editable OSINT preview items from filled text and image criteria."""

    items = []
    seen_values = set()

    for item in criteria or []:
        field = item.get("field")
        value = str(item.get("value") or "").strip()

        if field not in OSINT_ELIGIBLE_FIELDS or not value:
            continue

        deduplication_key = (field, value)

        if deduplication_key in seen_values:
            continue

        seen_values.add(deduplication_key)
        approval_item = {
            "id": uuid.uuid4().hex,
            "field": field,
            "label": OSINT_FIELD_LABELS.get(field, field),
            "value": value
        }

        if field == "face_image":
            if face_upload is None:
                continue

            approval_item.update(
                {
                    "filename": face_upload.name,
                    "content_type": face_upload.type or "application/octet-stream",
                    "file_bytes": face_upload.getvalue()
                }
            )

        items.append(approval_item)

    return items


def render_osint_approval_panel():
    """Show approved-preview OSINT items and let users remove before sending."""

    pending_items = st.session_state.get("pending_osint_items") or []

    if not pending_items:
        return

    st.markdown('<div class="section-title">Approve OSINT Submission</div>', unsafe_allow_html=True)
    status_panel(
        "Review the exact fields below. Remove anything you do not want to send, then approve the OSINT search.",
        "neutral"
    )

    remove_item_id = None

    for index, item in enumerate(pending_items):
        item_id = item.get("id") or uuid.uuid4().hex
        item["id"] = item_id
        field_col, value_col, remove_col = st.columns([1, 2.6, 0.7])

        with field_col:
            st.text_input(
                f"OSINT Field {index + 1}",
                value=item.get("label") or item.get("field") or "-",
                disabled=True,
                key=f"osint_preview_field_{item_id}"
            )

        with value_col:
            st.text_input(
                f"OSINT Value {index + 1}",
                value=item.get("value") or "",
                disabled=True,
                key=f"osint_preview_value_{item_id}"
            )

            if item.get("field") == "face_image" and item.get("file_bytes"):
                st.image(
                    item.get("file_bytes"),
                    width=170,
                    caption="Approved face image preview"
                )

        with remove_col:
            st.write("")
            if st.button(
                "Remove",
                key=f"remove_osint_preview_item_{item_id}",
                use_container_width=True
            ):
                remove_item_id = item_id

    if remove_item_id is not None:
        st.session_state["pending_osint_items"] = [
            item
            for item in pending_items
            if item.get("id") != remove_item_id
        ]
        st.rerun()

    approve_clicked = st.button(
        "Approve And Send To OSINT",
        type="primary",
        use_container_width=True
    )

    if approve_clicked:
        if not pending_items:
            status_panel("Select at least one OSINT item before submitting.", "danger")
            return

        approved_face_item = next(
            (
                item
                for item in pending_items
                if item.get("field") == "face_image"
            ),
            None
        )
        request_files = None

        if approved_face_item:
            request_files = {
                "face_image": (
                    approved_face_item.get("filename") or "face_image.jpg",
                    approved_face_item.get("file_bytes") or b"",
                    approved_face_item.get("content_type") or "application/octet-stream"
                )
            }

        response, result = post_request(
            OSINT_SUBMIT_URL,
            data={
                "targets_json": json.dumps(
                    [
                        {
                            "field": item.get("field"),
                            "value": item.get("value")
                        }
                        for item in pending_items
                    ]
                )
            },
            files=request_files
        )

        if response is None or response.status_code != 200:
            status_panel(result.get("message", "OSINT job could not be queued."), "danger")
            return

        osint_job = result.get("osint_job") or result.get("job") or {}

        if osint_job.get("job_id"):
            st.session_state["active_osint_job_id"] = osint_job.get("job_id")
            st.session_state.pop("last_osint_job", None)
            st.session_state.pop("pending_osint_items", None)
            status_panel("OSINT job approved and queued.", "success")
            st.rerun()


def render_osint_job_lookup_panel():
    """Let operators load any existing OSINT job by ID for review/testing."""

    st.markdown('<div class="section-title">Load OSINT Job</div>', unsafe_allow_html=True)
    lookup_col, action_col = st.columns([3, 1], gap="medium")

    with lookup_col:
        lookup_job_id = st.text_input(
            "OSINT Job ID",
            value=st.session_state.get("osint_lookup_job_id", "JOBDUMMY01"),
            key="osint_lookup_job_id",
            placeholder="Example: JOBDUMMY01"
        )

    with action_col:
        st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
        load_job_clicked = st.button(
            "View Job",
            use_container_width=True
        )

    if load_job_clicked:
        normalized_job_id = str(lookup_job_id or "").strip()

        if not normalized_job_id:
            status_panel("Enter an OSINT job ID to load.", "danger")
            return

        response, result = get_request(
            f"{OSINT_JOBS_URL}/{normalized_job_id}"
        )

        if response is None or response.status_code != 200:
            status_panel(result.get("message", "OSINT job could not be loaded."), "danger")
            return

        osint_job = result.get("osint_job") or result.get("job") or {}

        if not osint_job:
            status_panel("OSINT job response did not include job details.", "danger")
            return

        st.session_state["last_osint_job"] = osint_job
        st.session_state.pop("active_osint_job_id", None)
        status_panel(f"Loaded OSINT job {normalized_job_id}.", "success")


def format_news_date(value):
    """Format ISO timestamps for compact news display."""

    if not value:
        return "-"

    value = str(value)


    return value.replace("T", " ").split("+")[0][:19]


def news_excerpt(value, max_length=320):
    """Return a readable article/summary excerpt without breaking words badly."""

    value = str(value or "").strip()

    if len(value) <= max_length:
        return value

    return value[:max_length].rsplit(" ", 1)[0] + "..."


def render_news_entities(entities, limit=14):
    """Render news entities as compact chips."""

    entities = entities or []

    if not entities:
        st.caption("No extracted entities available for this news item.")
        return

    chips = []

    for entity in entities[:limit]:
        entity_name = html.escape(str(entity.get("entity_name") or "-"))
        entity_type = html.escape(str(entity.get("entity_type") or "entity"))
        frequency = entity.get("frequency") or 0
        chips.append(
            f'<span class="news-chip">{entity_name} <span class="news-chip-muted">{entity_type} - {frequency}</span></span>'
        )

    st.markdown(
        "".join(chips),
        unsafe_allow_html=True
    )


def render_news_source_cards(sources):
    """Render source counts as compact cards instead of a dense table."""

    sources = sources or []

    if not sources:
        st.caption("No source records found for this news item.")
        return

    items = []

    for source in sources[:8]:
        source_name = html.escape(str(source.get("source") or "Unknown"))
        article_count = source.get("article_count") or 0
        items.append(
            "".join([
                '<div class="news-source-item">',
                f'<div class="news-source-name">{source_name}</div>',
                f'<div class="news-source-count">{article_count} articles</div>',
                "</div>"
            ])
        )

    st.markdown(f'<div class="news-source-list">{"".join(items)}</div>', unsafe_allow_html=True)


def render_news_cluster_button(cluster, key_prefix):
    """Render one selectable news card and store selection when clicked."""

    cluster_id = cluster.get("cluster_id")
    title = cluster.get("cluster_name") or f"News {cluster_id}"
    article_count = cluster.get("actual_article_count") or cluster.get("article_count") or 0
    top_source = cluster.get("top_source") or "Mixed sources"
    updated_at = format_news_date(cluster.get("updated_at"))
    entities = cluster.get("entities") or []
    top_entities = ", ".join(
        str(entity.get("entity_name") or "")
        for entity in entities[:3]
        if entity.get("entity_name")
    )
    matched_fields = ", ".join(cluster.get("matched_fields") or [])

    match_html = ""

    if matched_fields:
        match_html = f'<div class="news-card-meta">Matched in: {html.escape(matched_fields)}</div>'

    entity_html = (
        f" - Key entities: {html.escape(top_entities)}"
        if top_entities
        else ""
    )
    card_html = "".join([
        '<div class="news-card">',
        f'<div class="news-card-title">{html.escape(str(title))}</div>',
        '<div class="news-card-meta">',
        f"News {cluster_id} - {article_count} articles - {html.escape(str(top_source))}",
        "</div>",
        '<div class="news-card-meta">',
        f"Updated: {updated_at}{entity_html}",
        "</div>",
        match_html,
        "</div>"
    ])

    st.markdown(card_html, unsafe_allow_html=True)

    if st.button(
        "Open News",
        key=f"{key_prefix}_{cluster_id}",
        use_container_width=True
    ):
        st.session_state["selected_news_cluster_id"] = cluster_id
        st.rerun()


def render_news_cluster_detail(cluster):
    """Render the selected news summary, sources, entities, and articles."""

    if not cluster:
        status_panel("Select a news item to view its intelligence summary.", "neutral")
        return

    brief_html = "".join([
        '<div class="news-brief">',
        f'<div class="news-brief-title">{html.escape(str(cluster.get("cluster_name") or "Untitled News"))}</div>',
        '<div class="news-brief-subtitle">',
        f'News ID: {cluster.get("cluster_id") or "-"} | Updated: {format_news_date(cluster.get("updated_at"))}',
        "</div>",
        '<div class="news-stat-grid">',
        '<div class="news-stat"><div class="news-stat-label">Articles</div>',
        f'<div class="news-stat-value">{cluster.get("actual_article_count") or cluster.get("article_count") or 0}</div></div>',
        '<div class="news-stat"><div class="news-stat-label">Sources</div>',
        f'<div class="news-stat-value">{len(cluster.get("sources") or [])}</div></div>',
        '<div class="news-stat"><div class="news-stat-label">Entities</div>',
        f'<div class="news-stat-value">{len(cluster.get("entities") or [])}</div></div>',
        "</div>",
        f'<div class="news-card-summary">{html.escape(news_excerpt(cluster.get("cluster_summary"), 900))}</div>',
        "</div>"
    ])

    st.markdown(brief_html, unsafe_allow_html=True)

    source_col, entity_col = st.columns([0.95, 1.45], gap="large")

    with source_col:
        st.markdown('<div class="section-title">Source Breakdown</div>', unsafe_allow_html=True)
        render_news_source_cards(cluster.get("sources") or [])

    with entity_col:
        st.markdown('<div class="section-title">Key Entities</div>', unsafe_allow_html=True)
        render_news_entities(cluster.get("entities") or [])

    st.markdown('<div class="section-title">Related Articles</div>', unsafe_allow_html=True)

    articles = cluster.get("articles") or []

    if not articles:
        status_panel("No articles are linked with this news item.", "warning")
        return

    for index, article in enumerate(articles, 1):
        title = article.get("title") or f"Article {index}"
        source = article.get("source") or "Unknown source"
        published_at = format_news_date(article.get("published_at"))

        with st.expander(f"{index}. {title[:140]}"):
            article_html = "".join([
                '<div class="news-article">',
                f'<div class="news-article-title">{html.escape(str(title))}</div>',
                f'<div class="news-card-meta">Source: {html.escape(str(source))} - Published: {published_at}</div>',
                f'<div class="news-article-body">{html.escape(news_excerpt(article.get("content"), 1000))}</div>',
                "</div>"
            ])
            st.markdown(article_html, unsafe_allow_html=True)

            if article.get("url"):
                st.markdown(
                    f"[Open source article]({article.get('url')})"
                )


def load_news_cluster_detail(cluster_id):
    """Fetch one news cluster detail payload from the backend."""

    if not cluster_id:
        return None

    response, result = get_request(
        f"{NEWS_CLUSTER_URL}/{cluster_id}"
    )

    if response is None or response.status_code != 200:
        status_panel(result.get("message", "News detail could not be loaded."), "danger")
        return None

    return result.get("cluster")


def load_common_news_topics(limit=500):
    """Fetch common searchable topics extracted from the news database."""

    response, result = get_request(
        NEWS_TOPICS_URL,
        params={
            "limit": limit
        }
    )

    if response is None or response.status_code != 200:
        status_panel(result.get("message", "Common topics could not be loaded."), "danger")
        return []

    return result.get("topics") or []


def filter_news_topic_suggestions(topics, query, limit=10):
    """Return topic suggestions that match what the user has typed."""

    query_text = str(query or "").strip().lower()

    if not query_text:
        return (topics or [])[:limit]

    starts_with_matches = []
    contains_matches = []
    seen_topics = set()

    for topic in topics or []:
        topic_name = str(topic.get("topic") or "").strip()

        if not topic_name:
            continue

        topic_key = topic_name.lower()

        if topic_key in seen_topics:
            continue

        seen_topics.add(topic_key)

        if topic_key.startswith(query_text):
            starts_with_matches.append(topic)
        elif query_text in topic_key:
            contains_matches.append(topic)

    return (starts_with_matches + contains_matches)[:limit]


def execute_news_search(query_text):
    """Run news search and persist results for the dashboard layout."""

    query_text = str(query_text or "").strip()

    if not query_text:
        status_panel("Enter a news topic, title, source, or entity to search.", "danger")
        return

    with st.spinner("Searching news intelligence data..."):
        response, result = get_request(
            NEWS_SEARCH_URL,
            params={
                "q": query_text,
                "limit": 20
            }
        )

    if response is None or response.status_code != 200:
        status_panel(result.get("message", "News search failed."), "danger")
        return

    st.session_state["news_search_result"] = result
    clusters = result.get("clusters") or []

    if clusters:
        st.session_state["selected_news_cluster_id"] = clusters[0].get("cluster_id")
        status_panel(
            f"Found {len(clusters)} matching news results. The strongest result is opened on the right.",
            "success"
        )
    else:
        st.session_state.pop("selected_news_cluster_id", None)
        status_panel("No news results matched this search.", "warning")


def build_news_data_signature(status_payload):
    """Build a stable change marker from the latest webhook and Docker DB state."""

    status_payload = status_payload or {}
    latest_batch = status_payload.get("latest_batch") or {}
    live_snapshot = status_payload.get("live_snapshot") or {}

    signature_payload = {
        "batch_id": latest_batch.get("batch_id"),
        "batch_status": latest_batch.get("status"),
        "batch_updated_at": latest_batch.get("updated_at"),
        "engine_completed_at": latest_batch.get("engine_completed_at"),
        "snapshot": {
            "clusters": live_snapshot.get("clusters"),
            "articles": live_snapshot.get("articles"),
            "cluster_entities": live_snapshot.get("cluster_entities"),
            "article_entities": live_snapshot.get("article_entities"),
            "latest_cluster_update": live_snapshot.get("latest_cluster_update"),
            "latest_article_published": live_snapshot.get("latest_article_published")
        }
    }

    return json.dumps(
        signature_payload,
        sort_keys=True,
        default=str
    )


@st.fragment(run_every="10s")
def render_news_auto_refresh_monitor():
    """Refresh News Intelligence when a webhook or Docker DB snapshot changes."""

    response, result = get_request(
        NEWS_SYNC_STATUS_URL,
        params={
            "include_live_snapshot": "true"
        }
    )

    if response is None or response.status_code != 200:
        st.caption("Automatic news updates are temporarily unavailable.")
        return

    current_signature = build_news_data_signature(result)
    previous_signature = st.session_state.get("news_data_signature")
    st.session_state["news_data_signature"] = current_signature

    if previous_signature is not None and current_signature != previous_signature:
        st.session_state.pop("news_common_topics_cache", None)
        st.session_state.pop("news_search_result", None)
        st.session_state.pop("selected_news_cluster_id", None)
        st.session_state["news_auto_refresh_message"] = (
            "New News Intelligence data was detected and loaded automatically."
        )
        st.rerun(scope="app")

    latest_batch = result.get("latest_batch") or {}
    snapshot_status = result.get("snapshot_status")
    batch_text = (
        f" Latest batch: {latest_batch.get('batch_id')} "
        f"({str(latest_batch.get('status') or '-').lower()})."
        if latest_batch.get("batch_id")
        else ""
    )

    if snapshot_status == "available":
        st.caption(f"Automatic news updates are active.{batch_text}")
    elif snapshot_status == "unavailable":
        st.caption(
            "Webhook updates are active. Docker PostgreSQL is temporarily unavailable."
            f"{batch_text}"
        )
    else:
        st.caption(f"Webhook updates are active.{batch_text}")


render_header()

selected_dashboard_section = render_sidebar_navigation()
render_active_section_header(selected_dashboard_section)


if selected_dashboard_section == "DRISHTI Intelligence":
    render_drishti_workspace()


if selected_dashboard_section == "Identity Search":
    st.markdown('<div class="section-title">Search Existing Identity Records</div>', unsafe_allow_html=True)

    if "identity_search_rows" not in st.session_state:
        st.session_state.identity_search_rows = [
            new_identity_search_row()
        ]

    ensure_identity_search_row_ids()

    add_col, reset_col, action_col = st.columns([1, 1, 2])

    with add_col:
        add_search_field = st.button(
            "+ Add Search Field",
            use_container_width=True
        )

    with reset_col:
        reset_search_fields = st.button(
            "Reset Fields",
            use_container_width=True
        )

    with action_col:
        search_clicked = st.button(
            "Search",
            type="primary",
            use_container_width=True
        )

    if add_search_field:
        st.session_state.identity_search_rows.append(
            new_identity_search_row()
        )
        st.rerun()

    if reset_search_fields:
        for row in st.session_state.identity_search_rows:
            clear_identity_search_widget_state(row.get("id"))

        st.session_state.identity_search_rows = [
            new_identity_search_row()
        ]
        st.session_state.pop("active_osint_job_id", None)
        st.session_state.pop("identity_search_result", None)
        st.session_state.pop("last_osint_job", None)
        st.session_state.pop("pending_osint_items", None)
        st.rerun()

    remove_row_id = None

    for index, row in enumerate(st.session_state.identity_search_rows):
        row_id = row.get("id")
        field_col, value_col, remove_col = st.columns([1.1, 2.4, 0.5])

        with field_col:
            current_field = row.get("field") or "Full Name"
            selected_label = st.selectbox(
                f"Field {index + 1}",
                list(SEARCH_OPTIONS.keys()),
                index=list(SEARCH_OPTIONS.keys()).index(current_field)
                if current_field in SEARCH_OPTIONS
                else 0,
                key=f"identity_search_field_{row_id}"
            )

        with value_col:
            if selected_label == "Face Image":
                identity_face_upload = st.file_uploader(
                    f"Value {index + 1}",
                    type=["jpg", "jpeg", "png"],
                    key=f"identity_search_face_{row_id}",
                    help="Upload one clear face image for database and approved OSINT search."
                )
                search_value = identity_face_upload.name if identity_face_upload else ""
            else:
                search_value = st.text_input(
                    f"Value {index + 1}",
                    value=row.get("value", ""),
                    placeholder=f"Enter {selected_label}",
                    key=f"identity_search_value_{row_id}"
                )

        with remove_col:
            st.write("")
            if len(st.session_state.identity_search_rows) > 1:
                if st.button(
                    "Remove",
                    key=f"remove_identity_search_row_{row_id}",
                    use_container_width=True
                ):
                    remove_row_id = row_id

        st.session_state.identity_search_rows[index] = {
            "id": row_id,
            "field": selected_label,
            "value": search_value
        }

    if remove_row_id is not None:
        clear_identity_search_widget_state(remove_row_id)
        st.session_state.identity_search_rows = [
            row
            for row in st.session_state.identity_search_rows
            if row.get("id") != remove_row_id
        ]
        st.rerun()
 # when osint polling re runs the streamlit page after few second so search clicked becomes false so db result disappreared..
    if search_clicked:
        st.session_state.pop("active_osint_job_id", None)
        st.session_state.pop("last_osint_job", None)
        st.session_state.pop("identity_search_result", None)
        st.session_state.pop("pending_osint_items", None)
        criteria, validation_errors = validate_identity_search_rows(
            st.session_state.identity_search_rows
        )
        text_criteria = [
            item
            for item in criteria
            if item.get("field") != "face_image"
        ]
        face_rows = [
            row
            for row in st.session_state.identity_search_rows
            if SEARCH_OPTIONS.get(row.get("field")) == "face_image"
        ]
        face_upload = None

        if face_rows:
            face_upload = st.session_state.get(
                f"identity_search_face_{face_rows[0].get('id')}"
            )

        if validation_errors:
            for error in validation_errors:
                status_panel(error, "danger")
        elif not criteria:
            status_panel("Please enter at least one search value.", "danger")
        else:
            if text_criteria:
                with st.spinner("Searching database records..."):
                    response, result = post_request(
                        ADVANCED_SEARCH_URL,
                        data={
                            "criteria_json": json.dumps(text_criteria),
                            "submit_osint": "false"
                        }
                    )

                if response is None or response.status_code != 200:
                    status_panel(result.get("message", "Search failed."), "danger")
                else:
                    st.session_state["identity_search_result"] = {
                        "total_matches": result.get("total_matches", 0),
                        "results": result.get("results", [])
                    }
                    st.session_state["identity_search_page_number"] = 1
                    st.session_state["identity_search_page_select"] = 1

            if face_upload is not None:
                with st.spinner("Queueing face search..."):
                    face_response, face_result = post_request(
                        FACE_SEARCH_JOBS_URL,
                        files=uploaded_file_payload("image", face_upload),
                        timeout=120
                    )

                if face_response is None or face_response.status_code != 200:
                    status_panel(
                        face_result.get("message", "Face search could not be queued."),
                        "danger"
                    )
                else:
                    face_job = face_result.get("job") or {}
                    st.session_state["active_face_search_job_id"] = face_job.get("job_id")
                    st.session_state["active_face_search_job"] = face_job
                    st.session_state.pop("last_face_search_job", None)
                    status_panel(
                        f"Face search queued successfully. Job ID: {face_job.get('job_id')}",
                        "success"
                    )

            st.session_state["pending_osint_items"] = build_osint_approval_items(
                criteria,
                face_upload=face_upload
            )

            if not st.session_state["pending_osint_items"]:
                status_panel(
                    "No filled search fields were available to send to OSINT.",
                    "warning"
                )

    if st.session_state.get("identity_search_result"):
        render_identity_search_results(st.session_state.get("identity_search_result"))

    if st.session_state.get("active_face_search_job_id"):
        render_face_search_job_status(
            st.session_state.get("active_face_search_job_id")
        )
    elif st.session_state.get("last_face_search_job"):
        render_face_search_job_card(
            st.session_state.get("last_face_search_job")
        )

    render_osint_approval_panel()
    render_osint_job_lookup_panel()

    if st.session_state.get("active_osint_job_id"):
        render_osint_job_status(st.session_state.get("active_osint_job_id"))
    elif st.session_state.get("last_osint_job"):
        st.markdown('<div class="section-title">OSINT Search</div>', unsafe_allow_html=True)
        render_osint_job_card(st.session_state.get("last_osint_job"))


if selected_dashboard_section == "News Intelligence":
    st.markdown(
        """
        <div class="news-brief">
            <div class="news-brief-title">News Intelligence</div>
            <div class="news-brief-subtitle">
                Explore top news, search by topic/source/entity, and open each news item to review
                its summary, source spread, key entities, and related articles.
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    render_news_auto_refresh_monitor()

    news_auto_refresh_message = st.session_state.pop(
        "news_auto_refresh_message",
        None
    )

    if news_auto_refresh_message:
        status_panel(news_auto_refresh_message, "success")

    if st.session_state.pop("news_intelligence_reset_requested", False):
        st.session_state["news_search_query"] = ""
        st.session_state["news_keyword_select"] = "Select keyword"
        st.session_state.pop("news_search_result", None)
        st.session_state.pop("selected_news_cluster_id", None)
        st.session_state.pop("news_search_pending_text", None)
        st.session_state.pop("news_topic_pending_query", None)
        st.session_state.pop("news_topic_should_search", None)

    pending_topic_query = (
        st.session_state.pop("news_topic_pending_query", None)
        or st.session_state.pop("news_search_pending_text", None)
    )

    if pending_topic_query:
        st.session_state["news_search_query"] = pending_topic_query
        st.session_state["news_keyword_select"] = "Select keyword"

    st.session_state.pop("news_topic_should_search", None)

    news_search_col, news_keyword_col, news_action_col, news_clear_col = st.columns([2.2, 1.35, 0.85, 0.85])

    with news_search_col:
        news_query = st.text_input(
            "Search news, article title, source, or entity",
            placeholder="Example: drone, Pakistan, Delhi, BSF, Twitter/X",
            key="news_search_query"
        )

    with news_keyword_col:
        common_topics = st.session_state.get("news_common_topics_cache")

        if common_topics is None:
            with st.spinner("Loading searchable keywords..."):
                common_topics = load_common_news_topics(500)
            st.session_state["news_common_topics_cache"] = common_topics

        topic_suggestions = filter_news_topic_suggestions(
            common_topics,
            news_query,
            limit=25
        )
        suggestion_options = [
            str(topic.get("topic") or "").strip()
            for topic in topic_suggestions
            if str(topic.get("topic") or "").strip()
        ]
        suggestion_options = list(dict.fromkeys(suggestion_options))[:25]
        keyword_options = ["Select keyword"] + suggestion_options

        if st.session_state.get("news_keyword_select") not in keyword_options:
            st.session_state["news_keyword_select"] = "Select keyword"

        selected_keyword = st.selectbox(
            "Relevant keywords",
            keyword_options,
            index=0,
            key="news_keyword_select"
        )

        if (
            selected_keyword != "Select keyword"
            and selected_keyword != str(news_query or "").strip()
        ):
            st.session_state["news_search_pending_text"] = selected_keyword
            st.rerun()

    with news_action_col:
        st.markdown('<div class="news-search-action-spacer"></div>', unsafe_allow_html=True)
        news_search_clicked = st.button(
            "Search News",
            type="primary",
            use_container_width=True
        )

    with news_clear_col:
        st.markdown('<div class="news-search-action-spacer"></div>', unsafe_allow_html=True)
        reset_news_search = st.button(
            "Reset",
            use_container_width=True
        )

    if reset_news_search:
        st.session_state["news_intelligence_reset_requested"] = True
        st.rerun()

    if news_search_clicked:
        execute_news_search(news_query)

    news_cluster_limit = st.selectbox(
        "Latest news to display",
        [10, 20, 30, 40, 50],
        index=0,
        key="news_cluster_display_limit"
    )

    with st.spinner("Loading latest news..."):
        top_response, top_result = get_request(
            NEWS_TOP_CLUSTERS_URL,
            params={
                "limit": news_cluster_limit
            }
        )

    top_clusters = []

    if top_response is None or top_response.status_code != 200:
        status_panel(top_result.get("message", "Top news could not be loaded."), "danger")
    else:
        top_clusters = top_result.get("clusters") or []

        if top_clusters and not st.session_state.get("selected_news_cluster_id"):
            st.session_state["selected_news_cluster_id"] = top_clusters[0].get("cluster_id")

    cluster_list_col, cluster_detail_col = st.columns([0.95, 1.75], gap="large")

    with cluster_list_col:
        search_result = st.session_state.get("news_search_result")

        if search_result:
            st.markdown('<div class="section-title">Search Results</div>', unsafe_allow_html=True)
            status_panel(
                f"Showing matches for: {html.escape(str(search_result.get('query') or '-'))}",
                "neutral"
            )

            for cluster in search_result.get("clusters") or []:
                render_news_cluster_button(
                    cluster,
                    "search_news_cluster"
                )

        st.markdown(
            f'<div class="section-title">Latest {news_cluster_limit} News</div>',
            unsafe_allow_html=True
        )

        if not top_clusters:
            status_panel("No news records were found in the news database.", "warning")
        else:
            for cluster in top_clusters:
                render_news_cluster_button(
                    cluster,
                    "top_news_cluster"
                )

    with cluster_detail_col:
        selected_cluster_id = st.session_state.get("selected_news_cluster_id")
        selected_cluster = load_news_cluster_detail(selected_cluster_id)
        render_news_cluster_detail(selected_cluster)


if selected_dashboard_section == "Document Validation":
    st.markdown('<div class="section-title">Validate Uploaded Government Document</div>', unsafe_allow_html=True)
    input_col, preview_col = st.columns([2, 1], gap="large")

    with input_col:
        selected_document_label = st.selectbox(
            "Document type",
            list(DOCUMENT_OPTIONS.keys())
        )
        document_type = DOCUMENT_OPTIONS[selected_document_label]
        manual_document_field = DOCUMENT_FIELD_BY_TYPE[document_type]
        manual_document_number = st.text_input(
            "Document number override",
            placeholder="Optional: use this if OCR misses the number"
        )
        uploaded_document = st.file_uploader(
            "Upload document image",
            type=["jpg", "jpeg", "png"],
            key="document_validation_upload"
        )
        validate_clicked = st.button(
            "Validate Document",
            type="primary",
            use_container_width=True
        )

    with preview_col:
        st.markdown('<div class="section-title">Upload Preview</div>', unsafe_allow_html=True)
        document_preview_job = (
            st.session_state.get("active_document_validation_job")
            or st.session_state.get("last_document_validation_job")
            or {}
        )
        render_persistent_upload_preview(
            uploaded_document,
            document_preview_job.get("uploaded_document_path"),
            "Awaiting document image.",
            260
        )

    if validate_clicked:
        if uploaded_document is None:
            status_panel("Please upload a document image.", "danger")
        else:
            progress_bar = st.progress(
                10,
                text="Preparing uploaded document..."
            )
            progress_bar.progress(
                50,
                text="Queueing background document validation..."
            )
            response, result = post_request(
                DOCUMENT_VALIDATION_JOBS_URL,
                data={
                    "document_type": document_type,
                    manual_document_field: manual_document_number
                },
                files=uploaded_file_payload("document", uploaded_document),
                timeout=120
            )
            progress_bar.progress(
                100,
                text="Background document validation request submitted."
            )

            if response is None or response.status_code != 200:
                status_panel(result.get("message", "Document validation failed."), "danger")
            else:
                document_job = result.get("job") or {}
                st.session_state["active_document_validation_job_id"] = document_job.get("job_id")
                st.session_state["active_document_validation_job"] = document_job
                st.session_state.pop("last_document_validation_job", None)
                status_panel(
                    f"Document validation queued successfully. Job ID: {document_job.get('job_id')}",
                    "success"
                )

    if st.session_state.get("active_document_validation_job_id"):
        render_document_validation_job_status(
            st.session_state.get("active_document_validation_job_id")
        )
    elif st.session_state.get("last_document_validation_job"):
        render_document_validation_job_card(
            st.session_state.get("last_document_validation_job")
        )

if selected_dashboard_section == "Face Search":
    st.markdown('<div class="section-title">Find A User By Face Image</div>', unsafe_allow_html=True)
    input_col, preview_col = st.columns([2, 1], gap="large")

    with input_col:
        st.selectbox(
            "Upload type",
            ["Face image only"]
        )
        uploaded_face_image = st.file_uploader(
            "Upload face image",
            type=["jpg", "jpeg", "png"],
            key="face_image_search"
        )
        face_search_clicked = st.button(
            "Search By Face",
            type="primary",
            use_container_width=True
        )

    with preview_col:
        st.markdown('<div class="section-title">Face Preview</div>', unsafe_allow_html=True)
        face_preview_job = (
            st.session_state.get("active_face_search_job")
            or st.session_state.get("last_face_search_job")
            or {}
        )
        render_persistent_upload_preview(
            uploaded_face_image,
            face_preview_job.get("uploaded_image_path"),
            "Awaiting face image.",
            240
        )

    if face_search_clicked:
        if uploaded_face_image is None:
            status_panel("Please upload a face image.", "danger")
        else:
            face_progress = st.progress(
                10,
                text="Preparing uploaded face image..."
            )
            face_progress.progress(
                50,
                text="Queueing background face search..."
            )
            response, result = post_request(
                FACE_SEARCH_JOBS_URL,
                files=uploaded_file_payload("image", uploaded_face_image),
                timeout=120
            )
            face_progress.progress(
                100,
                text="Background face search request submitted."
            )

            if response is None or response.status_code != 200:
                status_panel(result.get("message", "Face search failed."), "danger")
            else:
                face_job = result.get("job") or {}
                st.session_state["active_face_search_job_id"] = face_job.get("job_id")
                st.session_state["active_face_search_job"] = face_job
                st.session_state.pop("last_face_search_job", None)
                status_panel(
                    f"Face search queued successfully. Job ID: {face_job.get('job_id')}",
                    "success"
                )

    if st.session_state.get("active_face_search_job_id"):
        render_face_search_job_status(
            st.session_state.get("active_face_search_job_id")
        )
    elif st.session_state.get("last_face_search_job"):
        render_face_search_job_card(
            st.session_state.get("last_face_search_job")
        )


if selected_dashboard_section == "Document Validation":
    st.markdown('<div class="section-title">Manual Review Queue</div>', unsafe_allow_html=True)

    if st.session_state.get("manual_review_success_message"):
        status_panel(
            st.session_state.pop("manual_review_success_message"),
            "success"
        )

    filter_col, refresh_col = st.columns([3, 1])

    with filter_col:
        review_status = st.selectbox(
            "Case status",
            ["PENDING", "APPROVED", "REJECTED", "ALL"]
        )

    with refresh_col:
        st.write("")
        st.write("")
        refresh_reviews = st.button(
            "Refresh Queue",
            use_container_width=True
        )

    response, result = get_request(
        MANUAL_REVIEW_URL,
        params={
            "status": review_status
        }
    )

    if response is None or response.status_code != 200:
        status_panel(result.get("message", "Manual review queue could not be loaded."), "danger")
    else:
        cases = result.get("cases", [])
        st.metric("Cases Found", result.get("total_cases", 0))

        if refresh_reviews:
            st.rerun()

        if not cases:
            status_panel("No manual review cases found for this status.", "neutral")
        else:
            for review_case in cases:
                render_review_case(review_case)
                st.divider()


if selected_dashboard_section == "Admin Operations":
    st.markdown('<div class="section-title">Admin Identity Operations</div>', unsafe_allow_html=True)
    status_panel(
        "Only Employee ID and Full Name are required. Leave Driving Licence, Passport, Voter ID, PAN, or Aadhaar blank when a person does not have that document.",
        "neutral"
    )

    admin_response, admin_result = get_request(
        ADMIN_IDENTITIES_URL,
        params={
            "limit": 200
        }
    )

    admin_records = []

    if admin_response is None or admin_response.status_code != 200:
        status_panel(admin_result.get("message", "Admin records could not be loaded."), "danger")
    else:
        admin_records = admin_result.get("records", [])
        st.metric("Identity Records Loaded", admin_result.get("total_records", 0))

        with st.expander("View Loaded Records"):
            render_admin_records_table(admin_records)

    create_admin_tab, update_admin_tab, delete_admin_tab = st.tabs(
        [
            "Create Identity",
            "Update Identity",
            "Delete Identity"
        ]
    )

    with create_admin_tab:
        st.markdown("**OCR Autofill**")
        ocr_upload_col, ocr_action_col = st.columns([2.4, 0.8], gap="large")

        with ocr_upload_col:
            admin_ocr_documents = st.file_uploader(
                "Upload one or more documents to autofill fields",
                type=["jpg", "jpeg", "png"],
                accept_multiple_files=True,
                key="admin_create_ocr_document_uploads"
            ) or []

        with ocr_action_col:
            st.write("")
            admin_ocr_extract_clicked = st.button(
                "Extract And Fill",
                type="primary",
                use_container_width=True,
                key="admin_create_extract_and_fill"
            )

        admin_ocr_document_labels = {}
        document_labels = list(DOCUMENT_OPTIONS.keys())

        if admin_ocr_documents:
            st.caption("Choose the document type for each uploaded image before extracting.")
            for index, admin_ocr_document in enumerate(admin_ocr_documents):
                default_label = infer_document_label_from_filename(admin_ocr_document.name)
                default_index = document_labels.index(default_label)
                label_col, type_col = st.columns([1.5, 1], gap="large")

                with label_col:
                    st.markdown(f"**{admin_ocr_document.name}**")

                with type_col:
                    admin_ocr_document_labels[index] = st.selectbox(
                        "Document type",
                        document_labels,
                        index=default_index,
                        key=f"admin_create_ocr_type_{index}_{admin_ocr_document.name}"
                    )

        if admin_ocr_extract_clicked:
            if not admin_ocr_documents:
                status_panel("Upload at least one document image before extracting fields.", "danger")
            else:
                successful_documents = []
                empty_documents = []
                failed_documents = []

                with st.spinner("Running OCR and mapping fields into the form..."):
                    for index, admin_ocr_document in enumerate(admin_ocr_documents):
                        selected_label = admin_ocr_document_labels.get(
                            index,
                            infer_document_label_from_filename(admin_ocr_document.name)
                        )
                        response, result = post_request(
                            EXTRACT_DOCUMENT_FIELDS_URL,
                            data={
                                "document_type": DOCUMENT_OPTIONS[selected_label]
                            },
                            files=uploaded_file_payload("document", admin_ocr_document)
                        )

                        if response is None or response.status_code != 200:
                            failed_documents.append(
                                f"{admin_ocr_document.name}: {result.get('message', 'OCR extraction failed')}"
                            )
                            continue

                        extracted_data = result.get("extracted_data") or {}
                        changed_fields = apply_admin_create_ocr_prefill(extracted_data)

                        if changed_fields:
                            successful_documents.append(
                                f"{admin_ocr_document.name} ({', '.join(changed_fields)})"
                            )
                        else:
                            empty_documents.append(admin_ocr_document.name)

                if successful_documents:
                    status_panel(
                        "OCR autofill completed: " + "; ".join(successful_documents[:4]),
                        "success"
                    )

                if empty_documents:
                    status_panel(
                        "OCR ran but no matching create fields were found for: " + ", ".join(empty_documents),
                        "warning"
                    )

                if failed_documents:
                    status_panel(
                        "Some documents failed: " + "; ".join(failed_documents[:3]),
                        "danger"
                    )

        with st.form("admin_create_identity_form", clear_on_submit=False):
            identity_col, document_col, contact_col = st.columns(3, gap="large")

            with identity_col:
                st.markdown("**Core Identity**")
                admin_employee_id = st.text_input("Employee ID", key="admin_create_employee_id")
                admin_full_name = st.text_input("Full Name", key="admin_create_full_name")
                admin_date_of_birth = st.text_input("Date of Birth", placeholder="YYYY-MM-DD", key="admin_create_dob")
                admin_department = st.text_input("Department", key="admin_create_department")
                admin_state = st.text_input("State", key="admin_create_state")

            with document_col:
                st.markdown("**Optional Documents**")
                admin_aadhar_number = st.text_input("Aadhaar Number", key="admin_create_aadhaar")
                admin_pan_number = st.text_input("PAN Number", key="admin_create_pan")
                admin_voter_id_number = st.text_input("Voter ID Number", key="admin_create_voter")
                admin_driving_license_number = st.text_input("Driving Licence Number", key="admin_create_dl")
                admin_passport_number = st.text_input("Passport Number", key="admin_create_passport")

            with contact_col:
                st.markdown("**Contact And Photo**")
                admin_phone_number = st.text_input("Phone Number", key="admin_create_phone")
                admin_email = st.text_input("Email", key="admin_create_email")
                admin_photo = st.file_uploader(
                    "Profile Photo",
                    type=["jpg", "jpeg", "png"],
                    key="admin_create_photo"
                )
                if admin_photo is not None:
                    st.image(admin_photo, width=180)

            admin_create_submitted = st.form_submit_button(
                "Create Identity",
                use_container_width=True
            )

        if admin_create_submitted:
            if not admin_employee_id.strip():
                status_panel("Employee ID is required.", "danger")
            elif not admin_full_name.strip():
                status_panel("Full name is required.", "danger")
            else:
                files = uploaded_file_payload("photo", admin_photo) if admin_photo else None

                with st.spinner("Creating identity record..."):
                    response, result = post_request(
                        ADMIN_IDENTITIES_URL,
                        data={
                            "employee_id": admin_employee_id,
                            "full_name": admin_full_name,
                            "date_of_birth": admin_date_of_birth,
                            "aadhar_number": admin_aadhar_number,
                            "pan_number": admin_pan_number,
                            "voter_id_number": admin_voter_id_number,
                            "driving_license_number": admin_driving_license_number,
                            "passport_number": admin_passport_number,
                            "phone_number": admin_phone_number,
                            "email": admin_email,
                            "department": admin_department,
                            "state": admin_state
                        },
                        files=files
                    )

                if response is None or response.status_code != 200:
                    status_panel(result.get("message", "Identity creation failed."), "danger")
                else:
                    status_panel(result.get("message", "Identity created successfully."), "success")
                    render_person(result.get("record"), "Created Identity")

    with update_admin_tab:
        lookup_employee_id = st.text_input(
            "Employee ID to update",
            placeholder="Type Employee ID and press Enter",
            key="admin_update_employee_id_lookup"
        )
        selected_employee_id = lookup_employee_id.strip()
        selected_record = None

        if not selected_employee_id:
            status_panel("Type an Employee ID and press Enter to load that identity for editing.", "neutral")
        else:
            with st.spinner("Loading identity record..."):
                lookup_response, lookup_result = get_request(
                    f"{ADMIN_IDENTITIES_URL}/{selected_employee_id}"
                )

            if lookup_response is None or lookup_response.status_code != 200:
                status_panel(lookup_result.get("message", "Identity record could not be loaded."), "danger")
            else:
                selected_record = lookup_result.get("record") or {}
                status_panel(
                    f"Loaded identity {html.escape(selected_employee_id)}. Edit the fields below and submit.",
                    "success"
                )

        if selected_record:
            with st.form(f"admin_update_identity_form_{selected_employee_id}", clear_on_submit=False):
                identity_col, document_col, contact_col = st.columns(3, gap="large")

                with identity_col:
                    st.markdown("**Core Identity**")
                    update_full_name = st.text_input(
                        "Full Name",
                        value=selected_record.get("full_name") or "",
                        key=f"admin_update_full_name_{selected_employee_id}"
                    )
                    update_date_of_birth = st.text_input(
                        "Date of Birth",
                        value=selected_record.get("date_of_birth") or "",
                        key=f"admin_update_dob_{selected_employee_id}"
                    )
                    update_department = st.text_input(
                        "Department",
                        value=selected_record.get("department") or "",
                        key=f"admin_update_department_{selected_employee_id}"
                    )
                    update_state = st.text_input(
                        "State",
                        value=selected_record.get("state") or "",
                        key=f"admin_update_state_{selected_employee_id}"
                    )

                with document_col:
                    st.markdown("**Optional Documents**")
                    update_aadhar_number = st.text_input(
                        "Aadhaar Number",
                        value=selected_record.get("aadhar_number") or "",
                        key=f"admin_update_aadhaar_{selected_employee_id}"
                    )
                    update_pan_number = st.text_input(
                        "PAN Number",
                        value=selected_record.get("pan_number") or "",
                        key=f"admin_update_pan_{selected_employee_id}"
                    )
                    update_voter_id_number = st.text_input(
                        "Voter ID Number",
                        value=selected_record.get("voter_id_number") or "",
                        key=f"admin_update_voter_{selected_employee_id}"
                    )
                    update_driving_license_number = st.text_input(
                        "Driving Licence Number",
                        value=selected_record.get("driving_license_number") or "",
                        key=f"admin_update_dl_{selected_employee_id}"
                    )
                    update_passport_number = st.text_input(
                        "Passport Number",
                        value=selected_record.get("passport_number") or "",
                        key=f"admin_update_passport_{selected_employee_id}"
                    )

                with contact_col:
                    st.markdown("**Contact And Photo**")
                    update_phone_number = st.text_input(
                        "Phone Number",
                        value=selected_record.get("phone_number") or "",
                        key=f"admin_update_phone_{selected_employee_id}"
                    )
                    update_email = st.text_input(
                        "Email",
                        value=selected_record.get("email") or "",
                        key=f"admin_update_email_{selected_employee_id}"
                    )
                    update_photo = st.file_uploader(
                        "Replace Profile Photo",
                        type=["jpg", "jpeg", "png"],
                        key=f"admin_update_photo_{selected_employee_id}"
                    )
                    if selected_record.get("photo_path"):
                        photo_path = resolve_photo_path(selected_record.get("photo_path"))
                        if photo_path and os.path.exists(photo_path):
                            st.image(photo_path, width=160)

                admin_update_submitted = st.form_submit_button(
                    "Update Identity",
                    use_container_width=True
                )

            if admin_update_submitted:
                if not update_full_name.strip():
                    status_panel("Full name is required.", "danger")
                else:
                    files = uploaded_file_payload("photo", update_photo) if update_photo else None

                    with st.spinner("Updating identity record..."):
                        response, result = post_request(
                            f"{ADMIN_IDENTITIES_URL}/{selected_employee_id}/update",
                            data={
                                "full_name": update_full_name,
                                "date_of_birth": update_date_of_birth,
                                "aadhar_number": update_aadhar_number,
                                "pan_number": update_pan_number,
                                "voter_id_number": update_voter_id_number,
                                "driving_license_number": update_driving_license_number,
                                "passport_number": update_passport_number,
                                "phone_number": update_phone_number,
                                "email": update_email,
                                "department": update_department,
                                "state": update_state
                            },
                            files=files
                        )

                    if response is None or response.status_code != 200:
                        status_panel(result.get("message", "Identity update failed."), "danger")
                    else:
                        status_panel(result.get("message", "Identity updated successfully."), "success")
                        render_person(result.get("record"), "Updated Identity")

    with delete_admin_tab:
        if not admin_records:
            status_panel("Load records before deleting an identity.", "warning")
        else:
            employee_options = [
                record.get("employee_id")
                for record in admin_records
                if record.get("employee_id")
            ]
            delete_employee_id = st.selectbox(
                "Select identity to delete",
                employee_options,
                key="admin_delete_selected_employee"
            )
            delete_record = next(
                (
                    record
                    for record in admin_records
                    if record.get("employee_id") == delete_employee_id
                ),
                {}
            )

            if delete_record:
                render_person(delete_record, "Selected Identity")

            confirm_delete = st.checkbox(
                f"I understand this will delete employee {delete_employee_id}",
                key="admin_confirm_delete"
            )
            delete_clicked = st.button(
                "Delete Identity",
                use_container_width=True,
                disabled=not confirm_delete
            )

            if delete_clicked:
                with st.spinner("Deleting identity record..."):
                    response, result = post_request(
                        f"{ADMIN_IDENTITIES_URL}/{delete_employee_id}/delete"
                    )

                if response is None or response.status_code != 200:
                    status_panel(result.get("message", "Identity delete failed."), "danger")
                else:
                    status_panel(result.get("message", "Identity deleted successfully."), "success")
                    st.rerun()