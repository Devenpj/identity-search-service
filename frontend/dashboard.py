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

import requests
import streamlit as st


API_URL = "http://127.0.0.1:8000/search-identity"
ADVANCED_SEARCH_URL = "http://127.0.0.1:8000/search-identity-advanced"
VALIDATE_ID_URL = "http://127.0.0.1:8000/validate-id"
EXTRACT_DOCUMENT_FIELDS_URL = "http://127.0.0.1:8000/extract-document-fields"
FACE_SEARCH_URL = "http://127.0.0.1:8000/search-by-face"
REGISTER_IDENTITY_URL = "http://127.0.0.1:8000/register-identity"
MANUAL_REVIEW_URL = "http://127.0.0.1:8000/manual-review-cases"
ADMIN_IDENTITIES_URL = "http://127.0.0.1:8000/admin/identities"
OSINT_JOBS_URL = "http://127.0.0.1:8000/api/v1/osint/jobs"
OSINT_SUBMIT_URL = "http://127.0.0.1:8000/api/v1/osint/jobs"
NEWS_TOP_CLUSTERS_URL = "http://127.0.0.1:8000/api/v1/news/clusters/top"
NEWS_SEARCH_URL = "http://127.0.0.1:8000/api/v1/news/search"
NEWS_TOPICS_URL = "http://127.0.0.1:8000/api/v1/news/topics"
NEWS_CLUSTER_URL = "http://127.0.0.1:8000/api/v1/news/clusters"


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
    "full_name": "Full Name",
    "username": "Username",
    "email": "Email",
    "phone_number": "Phone Number"
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
        "label": "Manual Review",
        "description": "Resolve document cases that need operator approval or record updates.",
        "accent": "#9a5b00"
    },
    {
        "label": "Admin Operations",
        "description": "Load, create, update, and delete identity records from the database.",
        "accent": "#087443"
    },
    {
        "label": "Register Identity",
        "description": "Register a new verified identity with documents and profile photo.",
        "accent": "#7c3aed"
    },
    {
        "label": "News Intelligence",
        "description": "Explore top news clusters, related articles, sources, and entities.",
        "accent": "#be185d"
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

    if isinstance(value, list):
        value = len(value)

    if isinstance(value, dict):
        value = json.dumps(value, ensure_ascii=False)

    value = str(value)
    escaped_value = html.escape(value)

    if value.startswith(("http://", "https://")):
        return (
            f'<a class="table-link" href="{escaped_value}" '
            f'target="_blank" rel="noopener noreferrer">{escaped_value}</a>'
        )

    return escaped_value


def render_light_table(rows, columns, empty_message):
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
            <table class="admin-table">
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


def render_header():
    """Render the dashboard title and summary header."""

    st.markdown(
        """
        <div class="app-header">
            <div class="eyebrow">Identity Verification Command Center</div>
            <h1 class="app-title">Search, validate, register, and match identities from one secure console</h1>
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

    if os.path.isabs(photo_path) and os.path.exists(photo_path):
        return photo_path

    project_root = os.path.abspath(
        os.path.join(
            os.path.dirname(__file__),
            ".."
        )
    )
    relative_path = photo_path.lstrip("/\\")
    candidates = [
        os.path.join(project_root, relative_path),
        os.path.join(project_root, "frontend", relative_path),
        os.path.abspath(relative_path)
    ]

    for candidate in candidates:
        if os.path.exists(candidate):
            return candidate

    return candidates[1]


def safe_json_response(response):
    """Return parsed backend JSON or a safe error payload for non-JSON replies."""

    try:
        return response.json()
    except ValueError:
        return {
            "status": "error",
            "message": response.text or "Backend returned a non-JSON response"
        }


def post_request(url, data=None, files=None):
    """POST to the backend and normalize connection/JSON errors."""

    try:
        response = requests.post(
            url,
            data=data,
            files=files,
            timeout=180
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
        if left_path and os.path.exists(left_path):
            st.image(left_path, width=210)
        else:
            st.warning("Image not available")

    with right:
        st.markdown(f'<div class="evidence-label">{right_label}</div>', unsafe_allow_html=True)
        if right_path and os.path.exists(right_path):
            st.image(right_path, width=210)
        else:
            st.warning("Image not available")


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


def render_osint_results(results):
    """Render OSINT provider results as dashboard tables instead of raw JSON."""

    results = results or {}
    username_results = results.get("username_results") or []
    instagram_results = results.get("instagram_results") or []
    all_matches = results.get("all_matches") or []

    metric_one, metric_two, metric_three = st.columns(3)
    metric_one.metric("Username Results", len(username_results))
    metric_two.metric("Instagram Results", len(instagram_results))
    metric_three.metric("All Matches", len(all_matches))

    st.markdown("**Username Results**")
    render_light_table(
        username_results,
        [
            ("Target", "target"),
            ("Platform", "platform"),
            ("URL", "url"),
            ("Status", "status")
        ],
        "No username results were returned."
    )

    st.markdown("**Instagram Results**")
    render_light_table(
        instagram_results,
        [
            ("Target", "target_username"),
            ("Platform", "platform"),
            ("Status", "status"),
            ("Bio", "extracted_data.bio"),
            ("Avatar URL", "extracted_data.avatar_url"),
            ("Top Posts", "extracted_data.top_posts")
        ],
        "No Instagram results were returned."
    )

    st.markdown("**Enriched Matches**")
    render_light_table(
        all_matches,
        [
            ("Platform", "platform"),
            ("URL", "url"),
            ("Bio", "enriched_data.bio"),
            ("Avatar URL", "enriched_data.avatar_url"),
            ("Local Avatar Path", "enriched_data.local_avatar_path")
        ],
        "No enriched matches were returned."
    )


OSINT_TERMINAL_STATUSES = {"COMPLETED", "FAILED"}


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
        render_osint_results(job.get("results"))
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


def render_identity_search_results(search_result):
    """Render the latest database identity search result stored in session state."""

    search_result = search_result or {}
    results = search_result.get("results") or []

    st.metric("Matches Found", search_result.get("total_matches", len(results)))

    if results:
        for index, person in enumerate(results, start=1):
            render_identity_match_reason(person)
            render_person(person, f"Match {index}")
            st.divider()
    else:
        status_panel("No matching identity record was found.", "warning")


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
    st.session_state.pop(f"remove_identity_search_row_{row_id}", None)


def validate_identity_search_rows(search_rows):
    """Validate search rows before database search and OSINT preview creation."""

    criteria = []
    errors = []

    for index, row in enumerate(search_rows or [], start=1):
        label = row.get("field") or f"Field {index}"
        field = SEARCH_OPTIONS.get(label)
        value = str(row.get("value") or "").strip()

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

    return criteria, errors


def build_osint_approval_items(criteria):
    """Build editable OSINT preview items from eligible search criteria."""

    items = []
    seen_values = set()

    for item in criteria or []:
        field = item.get("field")
        value = str(item.get("value") or "").strip()

        if field not in OSINT_ELIGIBLE_FIELDS or not value:
            continue

        if value in seen_values:
            continue

        seen_values.add(value)
        items.append(
            {
                "id": uuid.uuid4().hex,
                "field": field,
                "label": OSINT_FIELD_LABELS.get(field, field),
                "value": value
            }
        )

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
            }
        )

        if response is None or response.status_code != 200:
            status_panel(result.get("message", "OSINT job could not be queued."), "danger")
            return

        osint_job = result.get("osint_job") or {}

        if osint_job.get("job_id"):
            st.session_state["active_osint_job_id"] = osint_job.get("job_id")
            st.session_state.pop("last_osint_job", None)
            st.session_state.pop("pending_osint_items", None)
            status_panel("OSINT job approved and queued.", "success")
            st.rerun()


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
    """Render cluster entities as compact chips."""

    entities = entities or []

    if not entities:
        st.caption("No extracted entities available for this cluster.")
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
        st.caption("No source records found for this cluster.")
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
    """Render one selectable cluster card and store selection when clicked."""

    cluster_id = cluster.get("cluster_id")
    title = cluster.get("cluster_name") or f"Cluster {cluster_id}"
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
        f"Cluster {cluster_id} - {article_count} articles - {html.escape(str(top_source))}",
        "</div>",
        '<div class="news-card-meta">',
        f"Updated: {updated_at}{entity_html}",
        "</div>",
        match_html,
        "</div>"
    ])

    st.markdown(card_html, unsafe_allow_html=True)

    if st.button(
        "Open Cluster",
        key=f"{key_prefix}_{cluster_id}",
        use_container_width=True
    ):
        st.session_state["selected_news_cluster_id"] = cluster_id
        st.rerun()


def render_news_cluster_detail(cluster):
    """Render the selected cluster summary, sources, entities, and articles."""

    if not cluster:
        status_panel("Select a cluster to view its intelligence summary.", "neutral")
        return

    brief_html = "".join([
        '<div class="news-brief">',
        f'<div class="news-brief-title">{html.escape(str(cluster.get("cluster_name") or "Untitled Cluster"))}</div>',
        '<div class="news-brief-subtitle">',
        f'Cluster ID: {cluster.get("cluster_id") or "-"} | Updated: {format_news_date(cluster.get("updated_at"))}',
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
        status_panel("No articles are linked with this cluster.", "warning")
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
        status_panel(result.get("message", "Cluster detail could not be loaded."), "danger")
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
            f"Found {len(clusters)} matching clusters. The strongest result is opened on the right.",
            "success"
        )
    else:
        st.session_state.pop("selected_news_cluster_id", None)
        status_panel("No news clusters matched this search.", "warning")


render_header()

metric_one, metric_two, metric_three, metric_four = st.columns(4)
metric_one.metric("Verification Modes", "6")
metric_two.metric("Document Types", "5")
metric_three.metric("Database", "PostgreSQL")
metric_four.metric("Face Engine", "OpenCV")

selected_dashboard_section = render_sidebar_navigation()
render_active_section_header(selected_dashboard_section)


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

        if validation_errors:
            for error in validation_errors:
                status_panel(error, "danger")
        elif not criteria:
            status_panel("Please enter at least one search value.", "danger")
        else:
            with st.spinner("Searching database records..."):
                response, result = post_request(
                    ADVANCED_SEARCH_URL,
                    data={
                        "criteria_json": json.dumps(criteria),
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
                st.session_state["pending_osint_items"] = build_osint_approval_items(criteria)

                if not st.session_state["pending_osint_items"]:
                    status_panel(
                        "No OSINT eligible fields were provided. Add Username, Email, Phone Number, or Full Name to send OSINT.",
                        "warning"
                    )

    if st.session_state.get("identity_search_result"):
        render_identity_search_results(st.session_state.get("identity_search_result"))

    render_osint_approval_panel()

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
                Explore top clusters, search by topic/source/entity, and open each cluster to review
                its summary, source spread, key entities, and related articles.
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    pending_topic_query = st.session_state.pop("news_topic_pending_query", None)

    if pending_topic_query:
        st.session_state["news_search_query"] = pending_topic_query
        st.session_state["news_topic_should_search"] = pending_topic_query

    news_search_col, news_action_col, news_clear_col = st.columns([3, 0.95, 0.95])

    with news_search_col:
        news_query = st.text_input(
            "Search news, article title, source, or entity",
            placeholder="Example: drone, Pakistan, Delhi, BSF, Twitter/X",
            key="news_search_query"
        )

    with news_action_col:
        st.markdown('<div class="news-search-action-spacer"></div>', unsafe_allow_html=True)
        news_search_clicked = st.button(
            "Search News",
            type="primary",
            use_container_width=True
        )

    with news_clear_col:
        st.markdown('<div class="news-search-action-spacer"></div>', unsafe_allow_html=True)
        clear_news_search = st.button(
            "Clear",
            use_container_width=True
        )

    if clear_news_search:
        st.session_state.pop("news_search_result", None)
        st.session_state.pop("selected_news_cluster_id", None)
        st.rerun()

    topic_search_query = st.session_state.pop("news_topic_should_search", None)

    if topic_search_query:
        execute_news_search(topic_search_query)
    elif news_search_clicked:
        execute_news_search(news_query)

    with st.spinner("Loading top clusters..."):
        top_response, top_result = get_request(
            NEWS_TOP_CLUSTERS_URL,
            params={
                "limit": 10
            }
        )

    top_clusters = []

    if top_response is None or top_response.status_code != 200:
        status_panel(top_result.get("message", "Top news clusters could not be loaded."), "danger")
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

        st.markdown('<div class="section-title">Top 10 Clusters</div>', unsafe_allow_html=True)

        if not top_clusters:
            status_panel("No clusters were found in the news database.", "warning")
        else:
            for cluster in top_clusters:
                render_news_cluster_button(
                    cluster,
                    "top_news_cluster"
                )

    with cluster_detail_col:
        st.markdown('<div class="section-title">Common Topics</div>', unsafe_allow_html=True)
        topic_limit = st.selectbox(
            "Keywords to display",
            [5, 10, 30, 50],
            index=1,
            key="news_common_topic_limit"
        )

        with st.spinner("Loading common topics..."):
            common_topics = load_common_news_topics(topic_limit)

        selected_topic_query = None

        if not common_topics:
            status_panel("No common topics were found in the news database.", "warning")
        else:
            st.caption(
                f"Showing top {len(common_topics)} searchable keywords from cluster and article entity data."
            )
            topic_columns = st.columns(2)

            for topic_index, topic in enumerate(common_topics):
                topic_name = str(topic.get("topic") or "").strip()

                if not topic_name:
                    continue

                topic_label = topic_name if len(topic_name) <= 32 else f"{topic_name[:29]}..."

                with topic_columns[topic_index % len(topic_columns)]:
                    if st.button(
                        topic_label,
                        key=f"news_common_topic_{topic_limit}_{topic_index}_{topic.get('topic_key')}",
                        use_container_width=True
                    ):
                        selected_topic_query = topic_name

        if selected_topic_query:
            st.session_state["news_topic_pending_query"] = selected_topic_query
            st.rerun()

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
        if uploaded_document is not None:
            st.image(uploaded_document, width=260)
        else:
            status_panel("Awaiting document image.", "neutral")

    if validate_clicked:
        if uploaded_document is None:
            status_panel("Please upload a document image.", "danger")
        else:
            progress_bar = st.progress(
                5,
                text="Preparing uploaded document..."
            )
            progress_bar.progress(
                20,
                text="Checking selected document type..."
            )
            response, result = post_request(
                VALIDATE_ID_URL,
                data={
                    "document_type": document_type,
                    manual_document_field: manual_document_number
                },
                files=uploaded_file_payload("document", uploaded_document)
            )

            if response is None or response.status_code != 200:
                progress_bar.progress(
                    100,
                    text="Validation stopped."
                )
                status_panel(result.get("message", "Document validation failed."), "danger")
            else:
                progress_bar.progress(
                    70,
                    text="Reading OCR and matching database record..."
                )
                decision = result.get("decision", {})
                extracted_data = result.get("extracted_data", {})
                database_match = result.get("database_match")
                face_verification = result.get("face_verification", {})
                risk_assessment = result.get("risk_assessment", {})
                manual_review_case = result.get("manual_review_case")
                progress_bar.progress(
                    100,
                    text="Verification completed."
                )

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
        if uploaded_face_image is not None:
            st.image(uploaded_face_image, width=240)
        else:
            status_panel("Awaiting face image.", "neutral")

    if face_search_clicked:
        if uploaded_face_image is None:
            status_panel("Please upload a face image.", "danger")
        else:
            with st.spinner("Comparing uploaded face with database photos..."):
                response, result = post_request(
                    FACE_SEARCH_URL,
                    files=uploaded_file_payload("image", uploaded_face_image)
                )

            if response is None or response.status_code != 200:
                status_panel(result.get("message", "Face search failed."), "danger")
            else:
                database_match = result.get("database_match")
                face_verification = result.get("face_verification", {})

                if result.get("matched") and database_match:
                    status_panel("Yes, the uploaded face matched a database user. Details are shared below.", "success")
                else:
                    status_panel("No confident face match was found in the database.", "danger")

                render_face_evidence(
                    "Uploaded Face Image",
                    face_verification.get("uploaded_face_path"),
                    "Best Database Candidate",
                    face_verification.get("database_face_path")
                )

                score = face_verification.get("score")
                if score is not None:
                    st.caption(f"Best score: {score}")

                if face_verification.get("error"):
                    st.caption(face_verification.get("error"))

                if database_match:
                    render_person(database_match, "Matched User Details")


if selected_dashboard_section == "Manual Review":
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


if selected_dashboard_section == "Register Identity":
    st.markdown('<div class="section-title">Register A New Identity</div>', unsafe_allow_html=True)

    with st.form("register_identity_form", clear_on_submit=False):
        identity_col, document_col, photo_col = st.columns([1.15, 1.15, 0.9], gap="large")

        with identity_col:
            st.markdown("**Core Identity**")
            employee_id = st.text_input("Employee ID")
            full_name = st.text_input("Full Name")
            date_of_birth = st.text_input("Date of Birth", placeholder="YYYY-MM-DD")
            phone_number = st.text_input("Phone Number")
            email = st.text_input("Email")
            department = st.text_input("Department")
            state = st.text_input("State")

        with document_col:
            st.markdown("**Document Numbers**")
            aadhar_number = st.text_input("Aadhaar Number")
            pan_number = st.text_input("PAN Number")
            voter_id_number = st.text_input("Voter ID Number")
            driving_license_number = st.text_input("Driving Licence Number")
            passport_number = st.text_input("Passport Number")

        with photo_col:
            st.markdown("**Profile Photo**")
            profile_photo = st.file_uploader(
                "Upload user photo",
                type=["jpg", "jpeg", "png"],
                key="register_profile_photo"
            )
            if profile_photo is not None:
                st.image(profile_photo, width=210)

        submitted = st.form_submit_button(
            "Submit Identity",
            use_container_width=True
        )

    if submitted:
        if not employee_id.strip():
            status_panel("Employee ID is required.", "danger")
        elif not full_name.strip():
            status_panel("Full name is required.", "danger")
        elif profile_photo is None:
            status_panel("Please upload a user photo.", "danger")
        else:
            with st.spinner("Saving identity details and profile photo..."):
                response, result = post_request(
                    REGISTER_IDENTITY_URL,
                    data={
                        "employee_id": employee_id,
                        "full_name": full_name,
                        "date_of_birth": date_of_birth,
                        "aadhar_number": aadhar_number,
                        "pan_number": pan_number,
                        "voter_id_number": voter_id_number,
                        "driving_license_number": driving_license_number,
                        "passport_number": passport_number,
                        "phone_number": phone_number,
                        "email": email,
                        "department": department,
                        "state": state
                    },
                    files=uploaded_file_payload("photo", profile_photo)
                )

            if response is None or response.status_code != 200:
                status_panel(result.get("message", "Identity registration failed."), "danger")
            else:
                status_panel(result.get("message", "Identity registered successfully."), "success")
                registered_user = result.get("user")
                if registered_user:
                    render_person(registered_user, "Registered User Details")
