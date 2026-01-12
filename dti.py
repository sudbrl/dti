import streamlit as st
import pandas as pd
from fpdf import FPDF
from datetime import datetime
import os

# ==========================================
# ⚙️ GLOBAL CONFIGURATION
# ==========================================
LOAN_CONFIG = {
    "Personal Term Loan (PTL)": 2.0,       # 50% DTI
    "Personal OD": 2.0,                    # 50% DTI
    "Mortgage Loan": 2.0,                  # 50% DTI
    "Auto Loan": 2.0,                      # 50% DTI
    "Home Loan": 1.428,                    # 70% DTI
    "First Time Home Buyer": 1.25,         # 80% DTI
    "Education Loan": 2.0
}

DEFAULT_TENURE = {"Personal OD": 1, "Home Loan": 15, "First Time Home Buyer": 20}

# ==========================================
# 🎨 MODERN PREMIUM THEME & UI SCALING
# ==========================================
st.set_page_config(
    page_title="DTI Analysis Engine", 
    layout="wide", 
    page_icon="📊",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap');
    
    /* Global Typography */
    html, body, [class*="css"] {
        font-family: 'Manrope', -apple-system, BlinkMacSystemFont, sans-serif;
        color: #1a1f36;
        letter-spacing: -0.01em;
    }

    /* 90% Zoom / Scaling Effect */
    .block-container {
        max-width: 95% !important;
        transform: scale(0.90); 
        transform-origin: top center;
        width: 111% !important; 
    }
    
    /* Main Background */
    .main { 
        background: linear-gradient(135deg, #f8fafc 0%, #e0e7ff 100%);
    }
    
    /* Sidebar Container & Scrollbar Styling */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0f172a 0%, #1e293b 100%);
        box-shadow: 4px 0 24px rgba(0,0,0,0.12);
    }
    
    /* Sidebar Scrollbar Customization */
    section[data-testid="stSidebar"] ::-webkit-scrollbar {
        width: 8px;
        height: 8px;
    }
    section[data-testid="stSidebar"] ::-webkit-scrollbar-track {
        background: #1e293b; 
    }
    section[data-testid="stSidebar"] ::-webkit-scrollbar-thumb {
        background: #475569; 
        border-radius: 4px;
    }
    section[data-testid="stSidebar"] ::-webkit-scrollbar-thumb:hover {
        background: #64748b; 
    }
    
    [data-testid="stSidebar"] * {
        color: #f1f5f9;
    }
    
    /* Sidebar Inputs - Color Changed from Black to Dark Grey */
    [data-testid="stSidebar"] input,
    [data-testid="stSidebar"] .stSelectbox div[data-baseweb="select"] {
        background: rgba(255, 255, 255, 0.95) !important;
        color: #334155 !important; /* Changed from #0f172a (Black) to Slate Grey */
        font-weight: 600;
    }
    
    /* Buttons - Red Override for Primary */
    div.stButton > button[kind="primary"] {
        background-color: #ef4444 !important;
        border-color: #ef4444 !important;
        color: white !important;
        border-radius: 8px;
        font-weight: 600;
        transition: all 0.3s ease;
    }
    div.stButton > button[kind="primary"]:hover {
        background-color: #dc2626 !important;
        border-color: #dc2626 !important;
    }

    /* Metric Cards */
    .metric-card {
        background: linear-gradient(135deg, #ffffff 0%, #f8fafc 100%);
        padding: 1.5rem;
        border-radius: 16px;
        border: 1px solid #e2e8f0;
        box-shadow: 0 4px 16px rgba(0, 0, 0, 0.06);
    }
    
    .metric-value {
        font-size: 2rem;
        font-weight: 800;
        color: #0f172a;
        font-family: 'JetBrains Mono', monospace;
    }
    
    .metric-delta-positive { color: #10b981; font-weight: 700; font-size: 0.9rem; }
    .metric-delta-negative { color: #ef4444; font-weight: 700; font-size: 0.9rem; }

    /* Status Banners */
    .status-banner {
        padding: 1rem 1.5rem;
        border-radius: 12px;
        font-weight: 700;
        font-size: 1rem;
        text-align: center;
        margin: 1.5rem 0;
    }
    .status-banner-pass { background: #d1fae5; border: 2px solid #10b981; color: #065f46; }
    .status-banner-fail { background: #fee2e2; border: 2px solid #ef4444; color: #991b1b; }
    
    /* Scenario Badge */
    .scenario-badge {
        background: #dbeafe;
        border-left: 4px solid #3b82f6;
        padding: 1.25rem 1.5rem;
        border-radius: 12px;
        margin-bottom: 1.5rem;
    }
    
    .input-section {
        background: white;
        padding: 2rem;
        border-radius: 16px;
        border-left: 4px solid #3b82f6;
        box-shadow: 0 8px 32px rgba(0,0,0,0.08);
        margin-bottom: 2rem;
    }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 🧮 CALCULATION HELPERS
# ==========================================
def calculate_obligation(loan_type, principal, rate, tenure):
    if principal <= 0 or rate <= 0: return 0.0
    r_monthly = (rate / 100) / 12
    if "OD" in loan_type or "Overdraft" in loan_type:
        return principal * r_monthly
    else:
        if tenure <= 0: return 0.0
        n_months = tenure * 12
        try:
            return (principal * r_monthly * ((1 + r_monthly) ** n_months)) / (((1 + r_monthly) ** n_months) - 1)
        except: return 0.0

def run_waterfall_allocation(df, total_income):
    """
    PRIORITY LOGIC:
    1. Sort by Required Multiplier (Highest First).
    2. Allocate Income sequentially.
    3. Last item gets remaining income calculation.
    """
    # Sort by Multiplier Descending (Highest Priority First)
    df_sorted = df.sort_values(by='Required Multiplier', ascending=False).reset_index(drop=True)
    
    run_inc = total_income
    pass_flags = []
    act_covs = []
    snaps = []
    
    num_loans = len(df_sorted)
    
    for idx, row in df_sorted.iterrows():
        obl = row['Obligation']
        req_mult = row['Required Multiplier']
        req_amt = obl * req_mult
        
        snaps.append(run_inc)
        
        # Check if this is the LAST loan in the priority queue
        is_last_loan = (idx == num_loans - 1)
        
        if not is_last_loan:
            # Standard Allocation
            if run_inc >= req_amt:
                act_covs.append(req_mult) # Met requirement
                pass_flags.append(True)
                run_inc -= req_amt
            else:
                # Failed intermediate loan
                actual = run_inc / obl if obl > 0 else 0
                act_covs.append(actual)
                pass_flags.append(False)
                run_inc = 0 # Depleted
        else:
            # Final Loan Logic: Calculate using remaining income
            actual = run_inc / obl if obl > 0 else 0
            act_covs.append(actual)
            pass_flags.append(actual >= req_mult)
            # Income technically remains as is or depletes, doesn't matter for calc
            
    df_sorted['Pass_Status'] = pass_flags
    df_sorted['Actual Coverage'] = act_covs
    df_sorted['Available_Income_Snapshot'] = snaps
    
    return df_sorted

# ==========================================
# 📄 ENTERPRISE PDF ENGINE
# ==========================================
class PDFReport(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 14)
        self.set_text_color(15, 23, 42)
        self.cell(0, 10, 'DTI ANALYSIS REPORT', 0, 1, 'L')
        self.set_draw_color(59, 130, 246)
        self.set_line_width(0.5)
        self.line(10, 20, 200, 20)
        self.ln(10)
    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.set_text_color(100, 116, 139)
        self.cell(0, 10, f'Page {self.page_no()} | Generated by DTI Engine | {datetime.now().strftime("%B %d, %Y")}', 0, 0, 'C')

def generate_pdf(client, income, df_main_results, is_pass, exposure, shortfall, mode, active_s_name, active_s_rate, active_s_inc, raw_loans, matrix_scenarios, agg_dti, stressed_sources_list=None):
    pdf = PDFReport()
    pdf.add_page()
    
    # 1. EXECUTIVE SUMMARY
    pdf.set_font("Arial", "B", 12)
    pdf.set_text_color(15, 23, 42)
    pdf.cell(0, 8, "EXECUTIVE SUMMARY", 0, 1)
    pdf.set_draw_color(226, 232, 240)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(4)
    
    pdf.set_font("Arial", "", 10)
    pdf.cell(45, 6, "Client Name:", 0, 0); pdf.set_font("Arial", "B", 10); pdf.cell(145, 6, str(client), 0, 1)
    
    # Logic for Mode display
    display_mode = mode.upper()
    if "BASELINE" in display_mode or active_s_name == "Baseline (No Stress)":
        display_mode = "NORMAL - STRESS N/A"

    pdf.set_font("Arial", "", 10)
    pdf.cell(45, 6, "Analysis Date:", 0, 0); pdf.cell(55, 6, datetime.now().strftime("%B %d, %Y"), 0, 0)
    pdf.cell(45, 6, "Analysis Mode:", 0, 0); pdf.set_font("Arial", "B", 10); pdf.cell(0, 6, display_mode, 0, 1)
    
    pdf.set_font("Arial", "", 10)
    pdf.cell(45, 6, "Monthly Income:", 0, 0); pdf.cell(55, 6, f"Rs. {income:,.2f}", 0, 0)
    pdf.cell(45, 6, "Total Exposure:", 0, 0); pdf.cell(0, 6, f"Rs. {exposure:,.2f}", 0, 1)
    
    # Aggregate DTI Line - Removed "(Income ÷ Obligation)" per request
    pdf.cell(45, 6, "Aggregate Coverage:", 0, 0); 
    pdf.set_font("Arial", "B", 10); 
    pdf.cell(0, 6, f"{agg_dti:.2f}x", 0, 1)

    if shortfall > 0:
        pdf.set_text_color(239, 68, 68)
        pdf.set_font("Arial", "B", 10)
        pdf.cell(45, 6, "Income Shortfall:", 0, 0); pdf.cell(0, 6, f"Rs. {shortfall:,.2f} (CRITICAL DEFICIT)", 0, 1)
        pdf.set_text_color(0,0,0)

    # 2. SCENARIO DETAILS
    pdf.ln(6)
    pdf.set_font("Arial", "B", 12)
    pdf.set_text_color(15, 23, 42)
    pdf.cell(0, 8, "SCENARIO DETAILS", 0, 1)
    pdf.set_draw_color(226, 232, 240)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(4)
    
    pdf.set_fill_color(219, 234, 254)
    pdf.set_font("Arial", "B", 10)
    pdf.cell(190, 7, f"  Active Configuration: {active_s_name}", 1, 1, 'L', fill=True)
    
    if active_s_rate > 0 or active_s_inc > 0:
        pdf.set_font("Arial", "", 9)
        pdf.set_fill_color(248, 250, 252)
        pdf.cell(95, 6, f"Interest Rate Shock: +{active_s_rate:.2f}%", 1, 0, 'L', fill=True)
        pdf.cell(95, 6, f"Income Reduction: -{active_s_inc:.2f}%", 1, 1, 'L', fill=True)
        if stressed_sources_list:
            source_str = ", ".join(stressed_sources_list)
            pdf.ln(6)
            pdf.set_font("Arial", "I", 8)
            pdf.cell(190, 6, f"Stress Applied To: {source_str}", 0, 1, 'L')
    
    pdf.ln(3)
    res_text = "APPROVED - Within Risk Tolerance" if is_pass else "DECLINED - Exceeds Risk Limits"
    pdf.set_text_color(16, 185, 129) if is_pass else pdf.set_text_color(239, 68, 68)
    pdf.set_font("Arial", "B", 11)
    pdf.cell(0, 7, f"Assessment Result: {res_text}", 0, 1)
    pdf.set_text_color(0,0,0)

    # 3. PORTFOLIO BREAKDOWN
    pdf.ln(6)
    pdf.set_font("Arial", "B", 12)
    pdf.set_text_color(15, 23, 42)
    pdf.cell(0, 8, "PRIORITY ALLOCATION BREAKDOWN", 0, 1)
    pdf.set_draw_color(226, 232, 240)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(4)
    
    cols = [45, 25, 25, 25, 30, 20, 20]
    headers = ["Facility Type", "Principal", "Payment", "Rem. Inc.", "Actual Cov.", "Required", "Status"]
    pdf.set_font("Arial", "B", 8)
    pdf.set_fill_color(241, 245, 249)
    for i, h in enumerate(headers): pdf.cell(cols[i], 7, h, 1, 0, 'C', fill=True)
    pdf.ln()
    
    pdf.set_font("Arial", "", 8)
    for idx, row in df_main_results.iterrows():
        fill = (idx % 2 == 0)
        pdf.set_fill_color(255, 255, 255) if not fill else pdf.set_fill_color(248, 250, 252)
        
        pdf.cell(cols[0], 7, str(row['Loan Type']), 1, 0, 'L', fill)
        pdf.cell(cols[1], 7, f"{row['Amount']:,.0f}", 1, 0, 'R', fill)
        pdf.cell(cols[2], 7, f"{row['Obligation']:,.0f}", 1, 0, 'R', fill)
        pdf.cell(cols[3], 7, f"{row['Available_Income_Snapshot']:,.0f}", 1, 0, 'R', fill)
        
        cov_txt = f"{row['Actual Coverage']:.2f}x"
        pdf.cell(cols[4], 7, cov_txt, 1, 0, 'C', fill)
        pdf.cell(cols[5], 7, f"{row['Required Multiplier']:.2f}x", 1, 0, 'C', fill)
        
        status = "PASS" if row['Pass_Status'] else "FAIL"
        if status == "FAIL": pdf.set_text_color(239, 68, 68)
        else: pdf.set_text_color(16, 185, 129)
        pdf.cell(cols[6], 7, status, 1, 1, 'C', fill)
        pdf.set_text_color(0,0,0)
    
    return pdf.output(dest='S').encode('latin-1')

# ==========================================
# 🏠 APP LOGIC
# ==========================================
if 'loans' not in st.session_state: st.session_state.loans = []
if 'income_sources' not in st.session_state: st.session_state.income_sources = [] 
if 'custom_scenarios' not in st.session_state: st.session_state.custom_scenarios = []

# --- SIDEBAR CONFIGURATION ---
with st.sidebar:
    st.markdown("# ⚙️ Configuration Panel")
    st.markdown("---")
    
    st.markdown("### 💰 Income Configuration")
    inc_mode = st.radio("Income Entry Method", ["Single Total", "Multiple Sources"], horizontal=True)
    gross_income = 0.0
    
    if inc_mode == "Single Total":
        gross_income = st.number_input("Monthly Gross Income (Rs.)", value=150000.0, step=5000.0)
    else:
        c1, c2 = st.columns([1.5, 1])
        src = c1.text_input("Income Source")
        amt = c2.number_input("Amount (Rs.)", min_value=0.0)
        
        # Red Button for Add Source
        if st.button("➕ Add Source", type="primary"): 
            if not src or src.strip() == "":
                st.error("❌ Please enter an Income Source name")
            elif amt <= 0:
                st.error("❌ Amount must be greater than 0")
            else:
                st.session_state.income_sources.append({"Source": src, "Amount": amt})
                st.success(f"✅ Added income source: {src}")
                st.rerun()
        if st.session_state.income_sources:
            st.dataframe(pd.DataFrame(st.session_state.income_sources), hide_index=True)
            if st.button("Clear All Sources", type="primary"): 
                st.session_state.income_sources = []
                st.rerun()
            gross_income = sum(x['Amount'] for x in st.session_state.income_sources)

    st.markdown("---")
    
    # STRESS TESTING CONTROLS
    st.markdown("### 📊 Stress Test Configuration")
    enable_stress = st.toggle("Enable Stress Testing", value=False)
    
    stress_rate_val = 0.0
    stress_inc_val = 0.0
    scenario_name = "Baseline (No Stress)"
    mode_label = "Baseline"
    matrix_data = {}
    stressed_sources_selection = []
    
    if enable_stress:
        # User requested specific/combination of income stress
        if inc_mode == "Multiple Sources" and len(st.session_state.income_sources) > 0:
            st.markdown("#### Income Stress Scope")
            all_source_names = [x['Source'] for x in st.session_state.income_sources]
            stressed_sources_selection = st.multiselect(
                "Select Income Sources to Stress",
                all_source_names,
                default=all_source_names,
                help="Only selected sources will be reduced by the stress percentage."
            )
        
        st.markdown("#### Custom Scenarios")
        with st.form("create_scenario_form"):
            st.markdown("➕ **Create New Scenario**")
            fc1, fc2 = st.columns(2)
            c_name = fc1.text_input("Scenario Name", placeholder="e.g. Rate Shock")
            c_rate = fc2.number_input("Rate Shock (+%)", 0.0, 50.0, 2.0, step=0.5)
            c_inc = st.number_input("Income Reduction (-%)", 0.0, 100.0, 10.0, step=5.0)
            
            submitted = st.form_submit_button("Save Scenario", type="primary")
            if submitted:
                if c_name:
                    st.session_state.custom_scenarios.append({"Name": c_name, "Rate": c_rate, "Income": c_inc})
                    st.success(f"✅ Saved: {c_name}")
                else:
                    st.error("Please enter a name")
        
        if len(st.session_state.custom_scenarios) > 0:
            c_names = [s['Name'] for s in st.session_state.custom_scenarios]
            active_c_name = st.selectbox("Active Scenario (For Top Summary)", c_names)
            
            active_s = next((s for s in st.session_state.custom_scenarios if s['Name'] == active_c_name), None)
            if active_s:
                stress_rate_val = active_s['Rate']
                stress_inc_val = active_s['Income']
                scenario_name = active_c_name
                mode_label = "Custom Stress"
            
            matrix_data = {s['Name']: {'Rate': s['Rate'], 'Income': s['Income']} for s in st.session_state.custom_scenarios}
            
            if st.button("🗑️ Clear Custom Scenarios", type="primary"):
                st.session_state.custom_scenarios = []
                st.rerun()
        else:
            st.warning("No custom scenarios created yet.")
            scenario_name = "None"

    st.markdown("---")
    # Red Button for Reset
    if st.button("🔄 Reset All Data", type="primary", use_container_width=True):
        st.session_state.loans = []
        st.session_state.income_sources = []
        st.session_state.custom_scenarios = []
        st.rerun()

# --- MAIN DASHBOARD ---
st.title("📊 DTI Analysis Engine")
st.markdown("Advanced income assessment and scenario analysis for loan portfolios")

# FACILITY INPUT SECTION
with st.container():
    st.markdown("<div class='input-section'><h5>➕ Add New Facility</h5>", unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns([2, 1.5, 1, 1])
    with c1: l_type = st.selectbox("Facility Type", list(LOAN_CONFIG.keys()))
    with c2: l_amt = st.number_input("Principal Amount (Rs.)", step=10000.0, min_value=0.0)
    with c3: l_rate = st.number_input("Interest Rate (%)", value=12.0, step=0.25)
    with c4: l_ten = st.number_input("Tenure (Years)", value=DEFAULT_TENURE.get(l_type, 5), min_value=1)
    
    c_opt, c_btn = st.columns([3, 1])
    with c_opt: use_man = st.checkbox("Use Fixed Monthly Payment (Override EMI Calculation)")
    man_emi = st.number_input("Fixed Monthly Payment (Rs.)", 0.0, step=1000.0) if use_man else 0.0
    
    if c_btn.button("Add to Portfolio", type="primary", use_container_width=True):
        # Validation
        errors = []
        if l_amt <= 0: errors.append("❌ Principal Amount must be greater than 0")
        if l_rate <= 0: errors.append("❌ Interest Rate must be greater than 0")
        if l_ten <= 0: errors.append("❌ Tenure must be at least 1 year")
        if use_man and man_emi <= 0: errors.append("❌ Fixed Monthly Payment must be greater than 0")
        
        if errors:
            for error in errors: st.error(error)
        else:
            std = calculate_obligation(l_type, l_amt, l_rate, l_ten)
            st.session_state.loans.append({
                "Loan Type": l_type, "Amount": l_amt, "Base Rate": l_rate, "Tenure": l_ten,
                "Base_Obligation": man_emi if use_man else std, "Required Multiplier": LOAN_CONFIG[l_type],
                "Is_Manual": use_man
            })
            st.success(f"✅ Added {l_type} to portfolio")
            st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

# PORTFOLIO ANALYSIS
if st.session_state.loans:
    if gross_income <= 0:
        st.error("⚠️ Please configure Monthly Gross Income in the sidebar before analyzing portfolio")
        st.stop()
    
    # -----------------------------
    # LOGIC 1: Income Calculation
    # -----------------------------
    eff_income = gross_income
    if enable_stress:
        if inc_mode == "Multiple Sources" and stressed_sources_selection:
            variable_income = sum(x['Amount'] for x in st.session_state.income_sources if x['Source'] in stressed_sources_selection)
            fixed_income = gross_income - variable_income
            stressed_variable = variable_income * (1.0 - (stress_inc_val / 100.0))
            eff_income = fixed_income + stressed_variable
        else:
            eff_income = gross_income * (1.0 - (stress_inc_val / 100.0))
    
    # -----------------------------
    # LOGIC 2: Base DataFrame Setup
    # -----------------------------
    df = pd.DataFrame(st.session_state.loans)
    tot_prin = df['Amount'].sum()
    
    def get_stress_row(row, s_rate):
        if row['Is_Manual']: return row['Base_Obligation'], row['Base Rate']
        new_r = row['Base Rate'] + s_rate
        return calculate_obligation(row['Loan Type'], row['Amount'], new_r, row['Tenure']), new_r

    # Apply ACTIVE scenario params for main view
    df[['Obligation', 'Effective_Rate']] = df.apply(lambda x: pd.Series(get_stress_row(x, stress_rate_val)), axis=1)
    
    # -----------------------------
    # LOGIC 3: Waterfall & Aggregates
    # -----------------------------
    df_result = run_waterfall_allocation(df, eff_income)
    
    total_obligation = df_result['Obligation'].sum()
    agg_dti = eff_income / total_obligation if total_obligation > 0 else 0
    overall_pass = all(df_result['Pass_Status'])
    
    income_shortfall = 0.0
    if not overall_pass:
        # Shortfall is tricky in waterfall, but we can approximate by Sum(Oblig * Mult) - Income
        req_ideal = sum(r['Obligation'] * r['Required Multiplier'] for _, r in df_result.iterrows())
        income_shortfall = max(0, req_ideal - eff_income)

    # -----------------------------
    # UI: Visuals
    # -----------------------------
    
    # Badge
    if enable_stress:
        inc_impact_text = ""
        if inc_mode == "Multiple Sources" and stressed_sources_selection:
            inc_impact_text = f"Income Impact: -{stress_inc_val:.2f}% (On Selected Sources)"
        else:
            inc_impact_text = f"Income Impact: -{stress_inc_val:.2f}% (Global)"
            
        st.markdown(f"""
        <div class='scenario-badge'>
            <div class='scenario-badge-title'>🎯 Active Scenario: {scenario_name}</div>
            <div class='scenario-badge-params'>Interest Rate Impact: +{stress_rate_val:.2f}% | {inc_impact_text}</div>
        </div>""", unsafe_allow_html=True)
    
    # Metrics
    k1, k2, k3, k4 = st.columns(4)
    with k1:
        st.markdown(f"<div class='metric-card'><div class='metric-label'>Total Exposure</div><div class='metric-value'>Rs.{tot_prin:,.0f}</div></div>", unsafe_allow_html=True)
    with k2:
        st.markdown(f"<div class='metric-card'><div class='metric-label'>Monthly Obligation</div><div class='metric-value'>Rs.{total_obligation:,.0f}</div></div>", unsafe_allow_html=True)
    with k3:
        # Aggregate DTI - Removed "Inc ÷ Oblig" text from screen here
        st.markdown(f"<div class='metric-card'><div class='metric-label'>Aggregate Coverage</div><div class='metric-value'>{agg_dti:.2f}x</div></div>", unsafe_allow_html=True)
    with k4:
        delta_class = "metric-delta-negative" if income_shortfall > 0 else "metric-delta-positive"
        delta_text = "Critical Deficit" if income_shortfall > 0 else "Adequate"
        st.markdown(f"<div class='metric-card'><div class='metric-label'>Income Shortfall</div><div class='metric-value'>Rs.{income_shortfall:,.0f}</div><div class='metric-delta {delta_class}'>{delta_text}</div></div>", unsafe_allow_html=True)

    # Status Banner
    if overall_pass:
        st.markdown("<div class='status-banner status-banner-pass'>✅ REQUEST APPROVED - Within Stipulated DTI Requirement</div>", unsafe_allow_html=True)
    else:
        st.markdown("<div class='status-banner status-banner-fail'>⚠️ PORTFOLIO DECLINED - Exceeds Stipulated DTI Requirement</div>", unsafe_allow_html=True)
        
    # ---------------------------------------------
    # UI: Multi-Scenario Breakdown (New Feature)
    # ---------------------------------------------
    
    # Helper to render table
    def render_facility_table(dataframe, caption_text=""):
        st.markdown(f"##### {caption_text}")
        disp = dataframe.copy()
        disp['Status'] = disp['Pass_Status'].apply(lambda x: "✅ PASS" if x else "❌ FAIL")
        disp['Amount'] = disp['Amount'].apply(lambda x: f"Rs.{x:,.0f}")
        disp['Obligation'] = disp['Obligation'].apply(lambda x: f"Rs.{x:,.0f}")
        disp['Available_Income_Snapshot'] = disp['Available_Income_Snapshot'].apply(lambda x: f"Rs.{x:,.0f}")
        disp['Actual Coverage'] = disp['Actual Coverage'].apply(lambda x: f"{x:.2f}x")
        disp['Effective_Rate'] = disp['Effective_Rate'].apply(lambda x: f"{x:.2f}%")
        
        st.dataframe(
            disp[['Loan Type', 'Amount', 'Effective_Rate', 'Obligation', 'Available_Income_Snapshot', 'Actual Coverage', 'Status']], 
            use_container_width=True, hide_index=True
        )
    
    st.markdown("### 📋 PORTFOLIO BREAKDOWN")
    
    # If custom scenarios exist, iterate and show all. Otherwise show active/baseline.
    if enable_stress and len(st.session_state.custom_scenarios) > 0:
        st.info("Displaying breakdowns for all defined scenarios (Priority Allocation applied).")
        
        for scen in st.session_state.custom_scenarios:
            s_name = scen['Name']
            s_rate = scen['Rate']
            s_inc_pct = scen['Income']
            
            # Recalculate Income for this scenario
            scen_income = 0.0
            if inc_mode == "Multiple Sources" and stressed_sources_selection:
                v_inc = sum(x['Amount'] for x in st.session_state.income_sources if x['Source'] in stressed_sources_selection)
                f_inc = gross_income - v_inc
                scen_income = f_inc + (v_inc * (1.0 - (s_inc_pct / 100.0)))
            else:
                scen_income = gross_income * (1.0 - (s_inc_pct / 100.0))
                
            # Recalculate Obligations
            temp_df = pd.DataFrame(st.session_state.loans)
            temp_df[['Obligation', 'Effective_Rate']] = temp_df.apply(lambda x: pd.Series(get_stress_row(x, s_rate)), axis=1)
            
            # Run Waterfall
            scen_res = run_waterfall_allocation(temp_df, scen_income)
            
            # Calculate Scenario Aggregate
            scen_tot_obl = scen_res['Obligation'].sum()
            scen_agg = scen_income / scen_tot_obl if scen_tot_obl > 0 else 0
            
            render_facility_table(scen_res, caption_text=f"Scenario: {s_name} (Aggregate Coverage: {scen_agg:.2f}x)")
            st.markdown("---")
            
    else:
        # Just show the active/single result calculated above
        render_facility_table(df_result, caption_text=f"Scenario: {scenario_name}")

    # ==========================================
    # 📄 EXPORT SECTION
    # ==========================================
    with st.expander("📄 Generate Comprehensive Report", expanded=True):
        st.markdown("Export a detailed PDF report with executive summary and scenario analysis.")
        
        ec1, ec2 = st.columns([3, 1])
        with ec1:
            report_name = st.text_input("Client/Portfolio Name", placeholder="Enter name here (e.g., John Doe - Q1 Review)", label_visibility="collapsed")
        
        with ec2:
            if st.button("🚀 Generate PDF", type="primary", use_container_width=True):
                if not report_name:
                    st.error("⚠️ Please enter a client name first.")
                else:
                    with st.spinner("Processing document..."):
                        sources_for_pdf = stressed_sources_selection if (inc_mode == "Multiple Sources" and enable_stress) else None
                        
                        pdf_bytes = generate_pdf(
                            report_name, gross_income, df_result, overall_pass, tot_prin, income_shortfall,
                            mode_label, scenario_name, stress_rate_val, stress_inc_val,
                            st.session_state.loans, matrix_data, agg_dti, sources_for_pdf
                        )
                        
                        st.session_state['generated_pdf'] = pdf_bytes
                        st.session_state['generated_pdf_name'] = f"Report_{report_name.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}.pdf"
                        
                        st.rerun()

        if 'generated_pdf' in st.session_state:
            st.markdown("---")
            st.success("✅ Report generated successfully.")
            st.download_button(
                label="⬇️ Download PDF Now",
                data=st.session_state['generated_pdf'],
                file_name=st.session_state['generated_pdf_name'],
                mime="application/pdf",
                type="secondary",
                use_container_width=True
            )

else:
    st.markdown("""
    <div style='text-align: center; padding: 4rem 2rem; background: linear-gradient(135deg, #ffffff 0%, #f8fafc 100%); border-radius: 16px; box-shadow: 0 4px 16px rgba(0,0,0,0.06);'>
        <h3 style='color: #475569; margin-bottom: 1rem;'>👋 Welcome to DTI Analysis Engine</h3>
        <p style='color: #64748b; font-size: 1.1rem;'>Get started by configuring your income sources and adding facilities using the sidebar controls.</p>
    </div>
    """, unsafe_allow_html=True)
