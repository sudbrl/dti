import streamlit as st
import pandas as pd
from fpdf import FPDF
from datetime import datetime
import plotly.graph_objects as go
import matplotlib.pyplot as plt
import tempfile
import os

# ==========================================
# ⚙️ CONFIGURATION
# ==========================================
LOAN_CONFIG = {
    "Personal Term Loan (PTL)": 2.0,       # Implied 50% DTI Cap
    "Personal OD": 2.0,                    # Implied 50% DTI Cap
    "Mortgage Loan": 2.0,                  # Implied 50% DTI Cap
    "Auto Loan": 2.0,                      # Implied 50% DTI Cap
    "Home Loan": 1.428,                    # Implied 70% DTI Cap
    "First Time Home Buyer": 1.25,         # Implied 80% DTI Cap
    "Education Loan": 2.0
}

DEFAULT_TENURE = {
    "Personal OD": 1,
    "Home Loan": 15,
    "First Time Home Buyer": 20
}

PRIORITY_RANKING = {
    "Personal Term Loan (PTL)": 1,
    "Home Loan": 2,
    "First Time Home Buyer": 3,
    "Auto Loan": 4,
    "Mortgage Loan": 5,
    "Education Loan": 6,
    "Personal OD": 99 
}

# ==========================================
# 🎨 PAGE & THEME SETUP
# ==========================================
st.set_page_config(
    page_title="Credit Risk | Stress Test Engine", 
    layout="wide", 
    page_icon="📉",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
        color: #1e293b;
    }
    .main { background-color: #f8fafc; }
    
    [data-testid="stSidebar"] {
        background-color: #0f172a; 
        border-right: 1px solid #334155;
    }
    [data-testid="stSidebar"] h2, [data-testid="stSidebar"] label, [data-testid="stSidebar"] .stMarkdown {
        color: #f1f5f9 !important;
    }
    [data-testid="stSidebar"] .stRadio p, [data-testid="stSidebar"] .stRadio div {
        color: #ffffff !important;
    }

    .stCard {
        background: white;
        padding: 1.5rem;
        border-radius: 12px;
        border: 1px solid #e2e8f0;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
        margin-bottom: 1rem;
    }
    
    .input-container {
        background: white;
        padding: 20px;
        border-radius: 12px;
        border-top: 4px solid #3b82f6; 
        box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1);
        margin-bottom: 25px;
    }

    .stress-banner {
        background: #fee2e2;
        border: 1px solid #ef4444;
        color: #991b1b;
        padding: 10px;
        border-radius: 8px;
        text-align: center;
        font-weight: 700;
        margin-bottom: 15px;
        animation: pulse 2s infinite;
    }
    
    @keyframes pulse {
        0% { box-shadow: 0 0 0 0 rgba(239, 68, 68, 0.4); }
        70% { box-shadow: 0 0 0 10px rgba(239, 68, 68, 0); }
        100% { box-shadow: 0 0 0 0 rgba(239, 68, 68, 0); }
    }

    thead tr th {
        background-color: #f1f5f9 !important;
        color: #334155 !important;
        font-weight: 600 !important;
        text-transform: uppercase;
        font-size: 0.85rem;
    }
    
    .stButton > button { border-radius: 6px; font-weight: 500; }
    
    .badge { padding: 4px 10px; border-radius: 6px; font-size: 0.85rem; font-weight: 600; }
    .badge-pass { background: #dcfce7; color: #166534; }
    .badge-fail { background: #fee2e2; color: #991b1b; }

</style>
""", unsafe_allow_html=True)

# --- HELPER FUNCTIONS ---
def calculate_obligation(loan_type, principal, rate, tenure):
    if principal <= 0 or rate <= 0: return 0.0
    r_monthly = (rate / 100) / 12
    
    if "OD" in loan_type or "Overdraft" in loan_type:
        return principal * r_monthly
    else:
        if tenure <= 0: return 0.0
        n_months = tenure * 12
        try:
            emi = (principal * r_monthly * ((1 + r_monthly) ** n_months)) / \
                  (((1 + r_monthly) ** n_months) - 1)
            return emi
        except: return 0.0

def create_matplotlib_chart(df):
    fig, ax = plt.subplots(figsize=(8, 4))
    categories = df['Loan Type']
    values = df['Obligation']
    bars = ax.barh(categories, values, color='#3b82f6', edgecolor='white')
    ax.set_title('Monthly Obligation Breakdown', fontsize=12, fontweight='bold', pad=15)
    ax.set_xlabel('Monthly Installment Amount', fontsize=9)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.grid(axis='x', linestyle='--', alpha=0.5)
    ax.bar_label(bars, fmt='{:,.2f}', padding=3, fontsize=9)
    plt.tight_layout()
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
    plt.savefig(temp_file.name, format='png', dpi=100)
    plt.close(fig)
    return temp_file.name

# --- PDF GENERATOR ---
class PDFReport(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 16)
        self.set_text_color(44, 62, 80)
        self.cell(0, 10, 'DTI Assessment Report', 0, 1, 'C')
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.set_text_color(128, 128, 128)
        self.cell(0, 10, f'Gen: {datetime.now().strftime("%Y-%m-%d %H:%M")} | DTI Analysis Engine', 0, 0, 'C')

def generate_pdf(client_name, gross_income, income_breakdown, df_loans, is_eligible, total_exposure, stress_active, stress_mode, stress_targets, stress_rate_add, stress_income_cut, income_stress_scope, income_stress_targets):
    pdf = PDFReport()
    pdf.add_page()
    
    # Stress Warning
    if stress_active:
        pdf.set_font("Arial", "B", 10)
        pdf.set_text_color(255, 0, 0)
        scope_text = "ALL LOANS" if stress_mode == "All Loans" else f"SELECTED LOANS ({', '.join(stress_targets)})"
        
        stress_details = []
        if stress_rate_add > 0: stress_details.append(f"Rate +{stress_rate_add:.2f}%")
        if stress_income_cut > 0: 
            inc_scope_msg = "PARTIAL INCOME" if income_stress_scope == "Specific Sources" else "ALL INCOME"
            stress_details.append(f"{inc_scope_msg} -{stress_income_cut:.2f}%")
        
        pdf.multi_cell(0, 5, f"*** STRESS TEST APPLIED: {scope_text} | {' & '.join(stress_details)} ***", 0, 'C')
        pdf.ln(5)

    # 1. SUMMARY
    pdf.set_text_color(0,0,0)
    pdf.set_font("Arial", "B", 11)
    pdf.cell(0, 8, "1. Executive Summary", 0, 1, 'L')
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(2)
    
    pdf.set_font("Arial", "", 10)
    pdf.cell(50, 7, "Client Identifier:", 0, 0)
    pdf.set_font("Arial", "B", 10)
    pdf.cell(0, 7, str(client_name), 0, 1)
    
    # --- Income Section ---
    pdf.set_font("Arial", "", 10)
    pdf.cell(50, 7, "Total Gross Income:", 0, 0)
    pdf.set_font("Arial", "B", 10)
    pdf.cell(0, 7, f"{gross_income:,.2f}", 0, 1)

    # Breakdown Table in PDF
    if income_breakdown:
        pdf.ln(2)
        pdf.set_font("Arial", "B", 9)
        pdf.cell(0, 6, "Income Breakdown & Stress Impact:", 0, 1)
        
        pdf.set_fill_color(245, 245, 245)
        pdf.set_font("Arial", "B", 8)
        pdf.cell(70, 6, "Source", 1, 0, 'L', fill=True)
        pdf.cell(40, 6, "Base Amount", 1, 0, 'R', fill=True)
        pdf.cell(40, 6, "Stressed Amount", 1, 1, 'R', fill=True)
        
        pdf.set_font("Arial", "", 8)
        
        for item in income_breakdown:
            base_amt = item['Amount']
            # --- STRESS CHECK LOGIC FOR PDF ---
            is_stressed = False
            if stress_income_cut > 0:
                if income_stress_scope == "All Income":
                    is_stressed = True
                elif income_stress_scope == "Specific Sources":
                    if item['Source'] in income_stress_targets:
                        is_stressed = True
            
            stressed_amt = base_amt * (1.0 - (stress_income_cut/100.0)) if is_stressed else base_amt
            
            pdf.cell(70, 6, str(item['Source']), 1, 0, 'L')
            pdf.cell(40, 6, f"{base_amt:,.2f}", 1, 0, 'R')
            
            # Highlight RED only if actually stressed
            if is_stressed and stress_income_cut > 0:
                pdf.set_text_color(192, 0, 0)
                pdf.cell(40, 6, f"{stressed_amt:,.2f} (-{stress_income_cut}%)", 1, 1, 'R')
                pdf.set_text_color(0, 0, 0)
            else:
                pdf.cell(40, 6, f"{stressed_amt:,.2f}", 1, 1, 'R')
        
        pdf.ln(2)

    pdf.set_font("Arial", "", 10)
    pdf.cell(50, 7, "Total Debt Exposure:", 0, 0)
    pdf.set_font("Arial", "B", 10)
    pdf.cell(0, 7, f"{total_exposure:,.2f}", 0, 1)

    # 2. DECISION
    pdf.ln(5)
    pdf.set_font("Arial", "B", 11)
    pdf.cell(0, 8, "2. System Determination", 0, 1, 'L')
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(2)

    if is_eligible:
        pdf.set_text_color(0, 128, 0) 
        status = "ELIGIBLE"
    else:
        pdf.set_text_color(192, 0, 0) 
        status = "NOT ELIGIBLE / DTI BREACH"

    pdf.set_font("Arial", "B", 14)
    pdf.cell(0, 10, status, 0, 1, 'L')
    pdf.set_text_color(0,0,0)

    # 3. TABLE
    pdf.ln(5)
    pdf.set_font("Arial", "B", 11)
    pdf.cell(0, 8, "3. Loan Breakdown (Amounts in 0.00)", 0, 1, 'L')
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(4)

    cols = [45, 25, 25, 25, 30, 20, 20] 
    headers = ["Facility", "Limit", "Obligation", "Avail. Inc", "Act Cov (Pre)", "Req Cov", "Result"]
    
    pdf.set_font("Arial", "B", 8)
    pdf.set_fill_color(240, 240, 240) 
    for i, h in enumerate(headers):
        pdf.cell(cols[i], 8, h, 1, 0, 'C', fill=True)
    pdf.ln()

    pdf.set_font("Arial", "", 7)
    
    sum_limit = 0
    sum_obligation = 0
    
    for _, row in df_loans.iterrows():
        sum_limit += row['Amount']
        sum_obligation += row['Obligation']
        
        pdf.cell(cols[0], 8, str(row['Loan Type']), 1)
        pdf.cell(cols[1], 8, f"{row['Amount']:,.0f}", 1, 0, 'R')
        pdf.cell(cols[2], 8, f"{row['Obligation']:,.2f}", 1, 0, 'R')
        pdf.cell(cols[3], 8, f"{row['Available_Income_Snapshot']:,.2f}", 1, 0, 'R')
        
        cov_val = row.get('Actual Coverage', 0)
        pre_cov_val = row.get('Pre_Stress_Coverage', 0)
        
        cov_text = f"{cov_val:.2f}x"
        if stress_active:
            cov_text += f" (Pre: {pre_cov_val:.2f}x)"
            
        pdf.cell(cols[4], 8, cov_text, 1, 0, 'C')
        pdf.cell(cols[5], 8, f"{row['Required Multiplier']:.2f}x", 1, 0, 'C')
        
        res = "PASS" if row['Pass_Status'] else "FAIL"
        if not row['Pass_Status']: pdf.set_text_color(192,0,0)
        pdf.cell(cols[6], 8, res, 1, 1, 'C')
        pdf.set_text_color(0,0,0)

    # --- TOTAL ROW ---
    pdf.set_font("Arial", "B", 7)
    pdf.set_fill_color(220, 230, 241) 
    
    # Recalculate Agg Coverage properly based on mixed stress
    agg_stress_inc = 0
    if income_breakdown:
        for item in income_breakdown:
            base_amt = item['Amount']
            is_stressed = False
            if stress_income_cut > 0:
                if income_stress_scope == "All Income": is_stressed = True
                elif income_stress_scope == "Specific Sources" and item['Source'] in income_stress_targets: is_stressed = True
            
            val = base_amt * (1.0 - (stress_income_cut/100.0)) if is_stressed else base_amt
            agg_stress_inc += val
    else:
        # Simple Mode
        factor = 1.0 - (stress_income_cut / 100.0)
        agg_stress_inc = gross_income * factor

    agg_coverage = (agg_stress_inc / sum_obligation) if sum_obligation > 0 else 0
    
    pdf.cell(cols[0], 8, "TOTAL PORTFOLIO", 1, 0, 'L', fill=True)
    pdf.cell(cols[1], 8, f"{sum_limit:,.0f}", 1, 0, 'R', fill=True)
    pdf.cell(cols[2], 8, f"{sum_obligation:,.2f}", 1, 0, 'R', fill=True)
    pdf.cell(cols[3], 8, "-", 1, 0, 'C', fill=True) 
    pdf.cell(cols[4], 8, f"{agg_coverage:.2f}x", 1, 0, 'C', fill=True) 
    pdf.cell(cols[5], 8, "-", 1, 0, 'C', fill=True) 
    pdf.cell(cols[6], 8, "-", 1, 1, 'C', fill=True) 

    # 4. CHART
    pdf.ln(10)
    pdf.set_font("Arial", "B", 11)
    pdf.cell(0, 8, "4. Visual Analysis", 0, 1, 'L')
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(5)
    
    try:
        chart_path = create_matplotlib_chart(df_loans)
        pdf.image(chart_path, x=15, w=180) 
        os.unlink(chart_path) 
    except Exception as e:
        pdf.cell(0, 10, f"Could not generate chart: {str(e)}", 0, 1)

    return pdf.output(dest='S').encode('latin-1')

# --- INITIALIZE STATE ---
if 'loans' not in st.session_state:
    st.session_state.loans = []
if 'income_sources' not in st.session_state:
    st.session_state.income_sources = [] 

# ==========================================
# 🧱 SIDEBAR CONTROLS
# ==========================================
with st.sidebar:
    st.markdown("### ⚙️ Profile Settings")
    
    income_mode = st.radio("Income Entry Mode:", ["Simple Total", "Detailed Breakdown"], horizontal=True)
    
    gross_income = 0.0
    
    if income_mode == "Simple Total":
        gross_income = st.number_input(
            "Gross Monthly Income", 
            min_value=0.0, 
            value=150000.0, 
            step=5000.0,
            format="%.2f"
        )
        st.session_state.income_sources = [] # Clear details if in simple mode
        
    else:
        st.markdown("<div style='font-size:0.85rem; margin-bottom:5px'>Add Income Sources</div>", unsafe_allow_html=True)
        
        c_i1, c_i2 = st.columns([1.5, 1])
        with c_i1:
            inc_src = st.text_input("Type (e.g. Salary)", key="inc_src_in")
        with c_i2:
            inc_amt = st.number_input("Amount", min_value=0.0, step=1000.0, key="inc_amt_in")
            
        if st.button("Add Income", use_container_width=True):
            if inc_src and inc_amt > 0:
                st.session_state.income_sources.append({"Source": inc_src, "Amount": inc_amt})
        
        if st.session_state.income_sources:
            st.markdown("---")
            temp_df = pd.DataFrame(st.session_state.income_sources)
            st.dataframe(temp_df, hide_index=True, use_container_width=True)
            
            if st.button("Clear Income List"):
                st.session_state.income_sources = []
                st.rerun()
                
            gross_income = sum(item['Amount'] for item in st.session_state.income_sources)
            st.markdown(f"**Total Gross: {gross_income:,.2f}**")
        else:
            gross_income = 0.0

    st.markdown("---")
    
    # --- STRESS TEST MODULE ---
    st.markdown("### ⚡ Stress Testing")
    
    stress_mode = st.radio(
        "Loan Stress Scope:",
        ["None", "All Loans", "Specific Types"],
        index=0
    )
    
    target_stress_types = []
    income_stress_targets = []
    income_stress_scope = "All Income" 
    
    stress_rate_add = 0.0
    stress_income_cut = 0.0

    if stress_mode != "None":
        st.markdown("""
        <div style='background: #334155; padding: 10px; border-radius: 5px; font-size: 0.85rem; color: #cbd5e1;'>
        Configure Stress Parameters.<br>Set to 0 to ignore specific criterion.
        </div>
        """, unsafe_allow_html=True)
        
        c_s1, c_s2 = st.columns(2)
        with c_s1:
            stress_rate_add = st.number_input("Rate Shock (+%)", min_value=0.0, value=2.0, step=0.25, format="%.2f")
        with c_s2:
            stress_income_cut = st.number_input("Inc. Shock (-%)", min_value=0.0, value=0.0, step=5.0, format="%.2f")
        
        if stress_mode == "Specific Types":
            existing_types = list(set([l['Loan Type'] for l in st.session_state.loans]))
            if not existing_types:
                st.warning("Add loans to select types.")
            else:
                target_stress_types = st.multiselect(
                    "Select Loans to Stress (Rate):",
                    options=existing_types,
                    default=existing_types
                )
        
        # === INCOME STRESS SCOPE (Conditional) ===
        if stress_income_cut > 0 and income_mode == "Detailed Breakdown" and len(st.session_state.income_sources) > 0:
            st.markdown("**Income Stress Scope:**")
            income_stress_scope = st.radio("Apply Drop To:", ["All Income", "Specific Sources"], horizontal=True)
            
            if income_stress_scope == "Specific Sources":
                existing_inc_srcs = list(set([i['Source'] for i in st.session_state.income_sources]))
                income_stress_targets = st.multiselect(
                    "Select Income to Stress:",
                    options=existing_inc_srcs,
                    default=existing_inc_srcs
                )

    st.markdown("---")
    
    if st.button("🗑️ Clear Portfolio", use_container_width=True):
        st.session_state.loans = []
        st.session_state.income_sources = []
        st.rerun()

# ==========================================
# 🏠 MAIN APPLICATION
# ==========================================
st.title("DTI Analysis Engine")
st.markdown("##### DTI Assessment & Stress Testing Tool")

# --- VISUAL ALERT FOR STRESS TEST ---
is_stress_active = (stress_mode != "None") and (stress_rate_add > 0 or stress_income_cut > 0)

if is_stress_active:
    msg = "ALL LOANS" if stress_mode == "All Loans" else "SPECIFIC LOANS"
    details = []
    if stress_rate_add > 0: details.append(f"+{stress_rate_add:.2f}% RATE")
    
    if stress_income_cut > 0:
        inc_msg = "FULL"
        if income_mode == "Detailed Breakdown" and income_stress_scope == "Specific Sources":
            inc_msg = "PARTIAL"
        details.append(f"{inc_msg} INCOME -{stress_income_cut:.2f}%")
    
    st.markdown(f"""
    <div class='stress-banner'>
        ⚠️ STRESS TEST ACTIVE ({msg}): {' & '.join(details)}
    </div>
    """, unsafe_allow_html=True)

# --- 1. INPUT SECTION ---
with st.container():
    st.markdown("<div class='input-container'>", unsafe_allow_html=True)
    st.markdown("#### ➕ Add Facility")
    
    c1, c2, c3, c4 = st.columns([2, 1.5, 1, 1])
    
    with c1:
        l_type = st.selectbox("Product Type", list(LOAN_CONFIG.keys()))
        def_tenure_val = DEFAULT_TENURE.get(l_type, 5)
    with c2:
        l_amt = st.number_input("Loan Amount", min_value=0.0, step=10000.0, format="%.2f")
    with c3:
        l_rate = st.number_input("Base Rate (%)", min_value=0.0, value=12.0, step=0.25, format="%.2f")
    with c4:
        l_tenure = st.number_input("Tenure (Y)", min_value=1, value=def_tenure_val, key=f"t_{l_type}")

    c_check, c_val, c_btn = st.columns([1.5, 1.5, 1], vertical_alignment="bottom")
    
    with c_check:
        use_manual = st.checkbox("Manual Obligation Override", help="Use a fixed EMI/Obligation amount.")
    
    with c_val:
        manual_val = 0.0
        if use_manual:
            manual_val = st.number_input("Fixed Monthly Obligation", min_value=0.0, format="%.2f")
            
    with c_btn:
        if st.button("Add to Portfolio", type="primary", use_container_width=True):
            std_obl = calculate_obligation(l_type, l_amt, l_rate, l_tenure)
            final_obl = manual_val if use_manual else std_obl
            
            if l_amt > 0:
                st.session_state.loans.append({
                    "Loan Type": l_type,
                    "Amount": l_amt,
                    "Base Rate": l_rate,
                    "Tenure": l_tenure,
                    "Base_Obligation": final_obl, 
                    "Required Multiplier": LOAN_CONFIG[l_type],
                    "Is_Manual": use_manual
                })
                st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

# --- 2. CALCULATION & RESULTS ---
if len(st.session_state.loans) > 0:
    
    df = pd.DataFrame(st.session_state.loans)
    
    # === LOAN STRESS LOGIC ===
    def apply_stress_logic(row):
        if row['Is_Manual']:
            return row['Base_Obligation'], row['Base Rate']
        
        should_rate_stress = False
        if stress_mode == "All Loans":
            should_rate_stress = True
        elif stress_mode == "Specific Types":
            if row['Loan Type'] in target_stress_types:
                should_rate_stress = True
        
        eff_rate = row['Base Rate'] + (stress_rate_add if should_rate_stress else 0.0)
        new_obl = calculate_obligation(row['Loan Type'], row['Amount'], eff_rate, row['Tenure'])
        
        return new_obl, eff_rate

    df[['Obligation', 'Effective_Rate']] = df.apply(
        lambda x: pd.Series(apply_stress_logic(x)), axis=1
    )

    # === INCOME STRESS LOGIC (STRICT CHECK) ===
    effective_income = 0.0
    
    if income_mode == "Simple Total":
        factor = 1.0 - (stress_income_cut / 100.0)
        effective_income = gross_income * factor
    else:
        # Detailed Logic
        running_total = 0.0
        for item in st.session_state.income_sources:
            amount = item['Amount']
            source = item['Source']
            
            is_stressed = False
            # STRICT CHECK: If Specific Sources mode is ON, verify source is in target list
            if stress_income_cut > 0 and is_stress_active:
                if income_stress_scope == "All Income":
                    is_stressed = True
                elif income_stress_scope == "Specific Sources":
                    if source in income_stress_targets: # <--- CRITICAL CHECK
                        is_stressed = True
            
            if is_stressed:
                amount = amount * (1.0 - (stress_income_cut / 100.0))
            
            running_total += amount
        effective_income = running_total

    # === CASCADING LOGIC ===
    df['Priority'] = df['Loan Type'].map(PRIORITY_RANKING).fillna(99)
    df = df.sort_values(by='Priority', ascending=True).reset_index(drop=True)
    
    running_income = effective_income
    act_coverages = []
    pre_stress_coverages = []
    avail_snapshots = []
    pass_flags = []
    
    last_idx = df.index[-1]
    overall_eligible = True
    total_policy_reserve = 0 
    
    for idx, row in df.iterrows():
        obl = row['Obligation'] 
        base_obl = row['Base_Obligation']
        policy = row['Required Multiplier']
        required_allocation = obl * policy
        
        avail_snapshots.append(running_income)
        
        pre_cov = (gross_income / base_obl) if base_obl > 0 else 999.0
        pre_stress_coverages.append(round(pre_cov, 2))
        
        if idx == last_idx:
            final_cov = running_income / obl if obl > 0 else 999.0
            act_coverages.append(round(final_cov, 2))
            
            if final_cov >= policy:
                pass_flags.append(True)
                total_policy_reserve += required_allocation
            else:
                pass_flags.append(False)
                overall_eligible = False
                total_policy_reserve += running_income 
        else:
            if running_income >= required_allocation:
                running_income -= required_allocation
                total_policy_reserve += required_allocation
                act_coverages.append(policy) 
                pass_flags.append(True)
            else:
                fail_cov = running_income / obl if obl > 0 else 0
                act_coverages.append(round(fail_cov, 2))
                pass_flags.append(False)
                overall_eligible = False
                running_income = 0 

    df['Available_Income_Snapshot'] = avail_snapshots
    df['Actual Coverage'] = act_coverages
    df['Pre_Stress_Coverage'] = pre_stress_coverages
    df['Pass_Status'] = pass_flags
    
    total_loan_amount = df['Amount'].sum()
    total_obligation = df['Obligation'].sum()

    # --- 3. VISUALIZATION DASHBOARD ---
    st.markdown("### 📊 Portfolio Analysis")
    
    col_kpi, col_chart = st.columns([2, 1])
    
    with col_kpi:
        k1, k2, k3 = st.columns(3)
        k1.metric("Total Exposure", f"{total_loan_amount:,.2f}")
        k2.metric("Mth. Obligation (Stressed)", f"{total_obligation:,.2f}", 
                  delta=f"+ Stress Applied" if is_stress_active else None, delta_color="inverse")
        k3.metric("Net Free Income", f"{running_income:,.2f}")
        
        st.markdown("---")
        
        if is_stress_active and stress_income_cut > 0:
            st.info(f"📉 **Income Impact**: Base: {gross_income:,.2f} ➔ Stressed: {effective_income:,.2f}")
        else:
            st.info(f"💰 **Total Gross Income**: {gross_income:,.2f}")

        if overall_eligible:
            st.success("✅ **APPROVED**: Income supports all obligations under current parameters.")
        else:
            st.error("❌ **REJECTED**: DTI Threshold breached. Insufficient income coverage.")

    with col_chart:
        free_cash = effective_income - total_policy_reserve
        if free_cash < 0: free_cash = 0
        buffer_amt = total_policy_reserve - total_obligation
        if buffer_amt < 0: buffer_amt = 0

        labels = ['Debt Payment', 'Risk Buffer', 'Disposable Inc.']
        vals = [total_obligation, buffer_amt, free_cash]
        colors = ['#ef4444', '#f59e0b', '#10b981']

        fig = go.Figure(data=[go.Pie(
            labels=labels,
            values=vals,
            hole=.5,
            marker_colors=colors,
            textinfo='label+value', 
            texttemplate='%{label}<br>%{value:,.2f}', 
            textposition='inside',
            insidetextorientation='horizontal'
        )])
        fig.update_layout(showlegend=False, margin=dict(t=10, b=10, l=10, r=10), height=250)
        st.plotly_chart(fig, use_container_width=True)

    # --- 4. DETAILED DATA TABLE ---
    st.markdown("### 📋 Cascading Calculation")
    
    disp = pd.DataFrame()
    disp["Facility"] = df["Loan Type"]
    disp["Amt / Limit"] = df["Amount"].apply(lambda x: f"{x:,.0f}")
    
    def format_rate(row):
        base = row['Base Rate']
        eff = row['Effective_Rate']
        if eff > base:
            return f"{eff:.2f}% (Stress)"
        return f"{base:.2f}%"

    disp["Rate (%)"] = df.apply(format_rate, axis=1)
    
    def format_obl(row):
        val = f"{row['Obligation']:,.2f}"
        if row['Is_Manual']: return val + " (Manual)"
        return val

    disp["Mth. Obligation"] = df.apply(format_obl, axis=1)
    disp["Avail. Inc"] = df["Available_Income_Snapshot"].apply(lambda x: f"{x:,.2f}")
    
    def format_coverage(row):
        curr = row['Actual Coverage']
        pre = row['Pre_Stress_Coverage']
        base_str = f"<b>{curr:.2f}x</b>"
        if is_stress_active:
             base_str += f" <span style='font-size:0.8em; color:#64748b'>(Pre: {pre:.2f}x)</span>"
        if curr < 1.0:
            return f"<span style='color:#ef4444'>{base_str}</span>"
        return base_str

    disp["Act. Cov"] = df.apply(format_coverage, axis=1)
    disp["Req. Cov"] = df["Required Multiplier"].apply(lambda x: f"{x:.2f}x")
    disp["Result"] = df["Pass_Status"].apply(lambda x: "<span class='badge badge-pass'>PASS</span>" if x else "<span class='badge badge-fail'>FAIL</span>")
    
    st.write(disp.to_html(escape=False, index=False, classes="table table-hover"), unsafe_allow_html=True)
    
    if is_stress_active:
        st.caption(f"*(Note: Income Shock applied: -{stress_income_cut:.2f}%. Rate Shock applied: +{stress_rate_add:.2f}%)*")

    # --- 5. EXPORT ---
    st.markdown("<br>", unsafe_allow_html=True)
    with st.expander("📄 Generate PDF Report"):
        c_name = st.text_input("Client Name")
        if c_name:
            pdf_data = generate_pdf(
                c_name, 
                gross_income,
                st.session_state.income_sources, 
                df, 
                overall_eligible, 
                total_loan_amount, 
                is_stress_active, 
                stress_mode, 
                target_stress_types,
                stress_rate_add,
                stress_income_cut,
                income_stress_scope,
                income_stress_targets
            )
            
            st.download_button(
                "⬇️ Download Report", 
                data=pdf_data, 
                file_name=f"Risk_Assessment_{datetime.now().strftime('%Y%m%d')}.pdf",
                mime="application/pdf",
                type="primary"
            )

else:
    st.info("👋 Start by adding a loan facility from the panel above.")
