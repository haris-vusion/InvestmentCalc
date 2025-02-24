import streamlit as st
import plotly.graph_objects as go
import random
import math
import os
from datetime import datetime
from dateutil.relativedelta import relativedelta

########################
# 1) TAX & UTILITY FUNCS
########################
BASE_PERSONAL_ALLOWANCE = 12570
BASE_BASIC_RATE_LIMIT = 50270
BASE_HIGHER_RATE_LIMIT = 125140

def calc_tax_annual(gross, pa, brt, hrt):
    """Simple tiered UK tax calculation for a single year's withdrawal."""
    if gross <= 0:
        return 0.0
    if gross <= pa:
        return 0.0
    tax = 0.0
    basic_portion = max(0, min(gross, brt) - pa)
    higher_portion = max(0, min(gross, hrt) - brt) if gross > brt else 0
    additional_portion = max(0, gross - hrt) if gross > hrt else 0

    tax += basic_portion * 0.20
    tax += higher_portion * 0.40
    tax += additional_portion * 0.45
    return tax

def calc_net_annual(gross, pa, brt, hrt):
    """Net after tax for a single year's withdrawal."""
    return gross - calc_tax_annual(gross, pa, brt, hrt)

def required_gross_annual_for_net_annual(net_annual, pa, brt, hrt):
    """
    How much gross do we need so that net is 'net_annual'?
    Binary search, to handle tax tiers.
    """
    if net_annual <= 0:
        return 0.0
    low, high = 0.0, 2_000_000.0
    for _ in range(50):
        mid = (low + high) / 2.0
        net = calc_net_annual(mid, pa, brt, hrt)
        if net < net_annual:
            low = mid
        else:
            high = mid
    return high

def get_tax_brackets_for_factor(factor):
    """Inflate bracket cutoffs by 'factor' for the year."""
    pa = BASE_PERSONAL_ALLOWANCE * factor
    brt = BASE_BASIC_RATE_LIMIT * factor
    hrt = BASE_HIGHER_RATE_LIMIT * factor
    return pa, brt, hrt

############################
# 2) ANNUAL SIMULATION LOGIC
############################
def simulate_investment_annual(
    initial_deposit,
    annual_deposit,
    deposit_growth_rate,    # e.g. 0.05 => +5% deposit each year
    annual_return_rate,     # e.g. 0.07 => 7% annual
    annual_inflation_rate,  # e.g. 0.02 => 2% annual
    annual_withdrawal_rate, # e.g. 0.04 => 4% rule
    target_annual_living_cost,  # e.g. 30000 net
    years,
    annual_volatility,      # e.g. 0.15 => 15% stdev
    start_date,
    mode="strict"           # or "four_percent"
):
    """
    We simulate year by year:
      1) Add an annual deposit (if not retired) -> grows by deposit_growth_rate each year
      2) Apply random annual return (draw from normal with mean=annual_return_rate, stdev=annual_volatility)
      3) Check if we can retire:
         - Condition: net(annual_withdrawal_rate * portfolio) >= current_annual_cost
      4) If retired, we withdraw once per year
         - If mode == "strict": only enough gross to net your living cost
         - If mode == "four_percent": withdraw (annual_withdrawal_rate * portfolio)
      5) Inflates living cost each year
      6) Also inflates tax brackets each year
    """
    portfolio_value = float(initial_deposit)
    current_annual_deposit = float(annual_deposit)
    current_annual_cost = float(target_annual_living_cost)
    tax_factor = 1.0  # to inflate tax brackets

    withdrawing = False
    start_withdrawal_date = None
    total_withdrawn = 0.0

    # track timeseries
    year_list = []
    dates_list = []
    portfolio_values = []
    withdrawal_values = []

    for yr in range(years):
        current_year_date = start_date + relativedelta(years=yr)

        # 1) deposit if not retired
        if not withdrawing:
            portfolio_value += current_annual_deposit
            # deposit grows for next year
            current_annual_deposit *= (1 + deposit_growth_rate)

        # 2) apply random annual return
        annual_return = random.gauss(annual_return_rate, annual_volatility)
        portfolio_value *= (1 + annual_return)

        # 3) check if we can retire if not already
        pa, brt, hrt = get_tax_brackets_for_factor(tax_factor)
        net_if_4_percent = calc_net_annual(annual_withdrawal_rate * portfolio_value, pa, brt, hrt)

        if (not withdrawing) and (net_if_4_percent >= current_annual_cost):
            withdrawing = True
            start_withdrawal_date = current_year_date

        # 4) if retired, withdraw once per year
        if withdrawing:
            if mode == "strict":
                # Only withdraw exactly enough to net your cost
                needed_gross = required_gross_annual_for_net_annual(current_annual_cost, pa, brt, hrt)
                if portfolio_value >= needed_gross:
                    withdrawal_amt = needed_gross
                else:
                    # partial if portfolio too small
                    withdrawal_amt = max(0, portfolio_value)
            else:  # mode == "four_percent"
                withdrawal_amt = annual_withdrawal_rate * portfolio_value
                if portfolio_value < withdrawal_amt:
                    withdrawal_amt = max(0, portfolio_value)

            portfolio_value -= withdrawal_amt
        else:
            withdrawal_amt = 0.0

        total_withdrawn += withdrawal_amt

        # track timeseries
        year_list.append(yr)
        dates_list.append(current_year_date)
        portfolio_values.append(portfolio_value)
        withdrawal_values.append(withdrawal_amt)

        # 5) inflate cost for next year
        current_annual_cost *= (1 + annual_inflation_rate)

        # 6) inflate tax brackets
        tax_factor *= (1 + annual_inflation_rate)

    return (dates_list, portfolio_values, withdrawal_values,
            start_withdrawal_date, total_withdrawn)

###############################
# 3) AVERAGE SIM & MONTE CARLO
###############################
def simulate_average_simulation_annual(
    initial_deposit,
    annual_deposit,
    deposit_growth_rate,
    annual_return_rate,
    annual_inflation_rate,
    annual_withdrawal_rate,
    target_annual_living_cost,
    years,
    annual_volatility,
    start_date,
    num_simulations,
    mode
):
    """Average out multiple runs of the above annual simulation."""
    aggregated_portfolio = [0.0] * years
    aggregated_withdrawals = [0.0] * years
    dates = None

    for _ in range(num_simulations):
        d, pv, wv, _, _ = simulate_investment_annual(
            initial_deposit,
            annual_deposit,
            deposit_growth_rate,
            annual_return_rate,
            annual_inflation_rate,
            annual_withdrawal_rate,
            target_annual_living_cost,
            years,
            annual_volatility,
            start_date,
            mode
        )
        if dates is None:
            dates = d
        for i in range(years):
            aggregated_portfolio[i] += pv[i]
            aggregated_withdrawals[i] += wv[i]

    avg_portfolio = [p / num_simulations for p in aggregated_portfolio]
    avg_withdrawals = [w / num_simulations for w in aggregated_withdrawals]
    return dates, avg_portfolio, avg_withdrawals

def run_monte_carlo_annual(
    initial_deposit,
    annual_deposit,
    deposit_growth_rate,
    annual_return_rate,
    annual_inflation_rate,
    annual_withdrawal_rate,
    target_annual_living_cost,
    years,
    annual_volatility,
    start_date,
    num_simulations,
    mode
):
    """
    We'll say a run is 'successful' if:
      (a) We eventually start withdrawing (i.e. can retire), AND
      (b) The portfolio is above zero at the end of the simulation.
    """
    successes = 0
    for _ in range(num_simulations):
        _, pv, _, wd_date, _ = simulate_investment_annual(
            initial_deposit,
            annual_deposit,
            deposit_growth_rate,
            annual_return_rate,
            annual_inflation_rate,
            annual_withdrawal_rate,
            target_annual_living_cost,
            years,
            annual_volatility,
            start_date,
            mode
        )
        if wd_date is not None and pv[-1] > 0:
            successes += 1
    return (successes / num_simulations) * 100

##############################
# 4) STREAMLIT DISPLAY FUNCS
##############################
def display_summary_for_average_annual(dates, portfolio, withdrawals):
    import streamlit as st
    first_withdraw_idx = None
    for i, w in enumerate(withdrawals):
        if w > 1e-9:
            first_withdraw_idx = i
            break

    total_withdrawn = sum(withdrawals)
    final_portfolio = portfolio[-1]

    st.subheader("Summary (Average Simulation)")

    if first_withdraw_idx is None:
        st.write("• The average simulation never reached the threshold to retire.")
        st.write(f"• Final average portfolio value: £{final_portfolio:,.2f}")
        st.write("• Total average withdrawn: £0.00")
    else:
        start_wd_date = dates[first_withdraw_idx]
        years_into_sim = (start_wd_date - dates[0]).days / 365.25
        st.write(f"• Retire withdrawals began on {start_wd_date.strftime('%Y-%m-%d')} (~{years_into_sim:.2f} years in).")
        st.write(f"• Final average portfolio value: £{final_portfolio:,.2f}")
        st.write(f"• Total average withdrawn: £{total_withdrawn:,.2f}")

def display_memes(probability):
    """Simple meme logic. Adjust or remove as needed."""
    good_memes_folder = "goodMemes"
    bad_memes_folder = "badMemes"

    import streamlit as st

    if probability >= 50:
        st.markdown("### Congratulations! It's a Good Outcome Meme Break")
        meme_folder = good_memes_folder
    else:
        st.markdown("### Ouch... It's a Bad Outcome Meme Break")
        meme_folder = bad_memes_folder

    try:
        all_files = os.listdir(meme_folder)
        image_files = [f for f in all_files if f.lower().endswith(('.png', '.jpg', '.jpeg', '.gif'))]
        if not image_files:
            st.write(f"No meme images found in '{meme_folder}'.")
            return
        chosen_meme = random.choice(image_files)
        meme_path = os.path.join(meme_folder, chosen_meme)
        col1, col2, col3 = st.columns([1, 2, 1])
        col2.image(meme_path, caption=chosen_meme, width=300)
    except Exception as e:
        st.write(f"Could not load memes from folder '{meme_folder}'")
        st.write(e)

##############################
# 5) MAIN APP (ANNUAL LOGIC)
##############################
def main():
    st.set_page_config(page_title="Haris' Lods of Emone (Annual)", layout="wide")

    st.title("Haris' Lods of Emone (Annual Simulation)")
    st.write(
        "This version simulates year by year, adding deposits (if not retired), "
        "applying annual returns, and then checking if you can retire. "
        "Once retired, you withdraw once per year according to the selected mode."
    )

    # Default parameter dictionary (all in ANNUAL terms, with percentages)
    default_params = {
        "start_date": datetime.today().date(),
        "initial_deposit": 10000,
        "annual_deposit": 6000,  # e.g. 500 per month x 12
        "annual_inflation_rate": 3.0,   # 3% annual
        "deposit_growth_rate": 2.0,     # 2% annual deposit growth
        "annual_return_rate": 7.0,      # 7% annual
        "annual_withdrawal_rate": 4.0,  # 4% rule
        "target_annual_living_cost": 30000,
        "years": 40,
        "annual_volatility": 10.0,      # 10% stdev
        "num_simulations": 50
    }

    # === SIDEBAR ===
    st.sidebar.header("Simulation Parameters (Annual)")
    user_start_date = st.sidebar.date_input(
        "Starting Date",
        value=default_params["start_date"]
    )
    user_initial_deposit = st.sidebar.number_input(
        "Initial Deposit (£)",
        min_value=0,
        value=default_params["initial_deposit"],
        step=1000
    )
    user_annual_deposit = st.sidebar.number_input(
        "Annual Deposit (£)",
        min_value=0,
        value=default_params["annual_deposit"],
        step=1000
    )
    user_annual_inflation_rate = st.sidebar.slider(
        "Annual Inflation Rate (%)",
        0.0, 10.0,
        default_params["annual_inflation_rate"], 0.1
    )
    user_deposit_growth_rate = st.sidebar.slider(
        "Annual Deposit Growth Rate (%)",
        0.0, 10.0,
        default_params["deposit_growth_rate"], 0.1
    )
    user_annual_return_rate = st.sidebar.slider(
        "Annual Return Rate (%)",
        0.0, 20.0,
        default_params["annual_return_rate"], 0.1
    )
    user_annual_withdrawal_rate = st.sidebar.slider(
        "Annual Withdrawal Rate (%)",
        0.0, 20.0,
        default_params["annual_withdrawal_rate"], 0.1
    )
    user_target_annual_living_cost = st.sidebar.number_input(
        "Target Net Annual Living Cost (£)",
        min_value=0,
        value=default_params["target_annual_living_cost"],
        step=1000
    )
    user_years = st.sidebar.slider(
        "Number of Years to Simulate",
        1, 60,
        default_params["years"]
    )
    user_annual_volatility = st.sidebar.slider(
        "Annual Volatility (%)",
        0.0, 50.0,
        default_params["annual_volatility"], 0.1
    )
    user_num_sims = st.sidebar.number_input(
        "Monte Carlo Simulations",
        min_value=10,
        value=default_params["num_simulations"],
        step=10
    )

    # Choose the mode:
    user_mode = st.sidebar.selectbox(
        "Withdrawal Mode",
        ("strict", "four_percent"),
        index=0,
        help="strict = only withdraw exactly enough to net your living cost; four_percent = always withdraw 4% once retired"
    )

    # Convert percentages => decimals
    user_annual_inflation_rate /= 100.0
    user_deposit_growth_rate /= 100.0
    user_annual_return_rate /= 100.0
    user_annual_withdrawal_rate /= 100.0
    user_annual_volatility /= 100.0

    # === RUN MONTE CARLO
    probability = run_monte_carlo_annual(
        user_initial_deposit,
        user_annual_deposit,
        user_deposit_growth_rate,
        user_annual_return_rate,
        user_annual_inflation_rate,
        user_annual_withdrawal_rate,
        user_target_annual_living_cost,
        user_years,
        user_annual_volatility,
        user_start_date,
        user_num_sims,
        user_mode
    )

    color = "#2ecc71" if probability >= 50 else "#e74c3c"
    st.markdown(
        f"""
        <div style="background-color: #1c1c1c; border-radius: 8px; padding: 15px; margin-bottom: 20px;">
            <div style="text-align:center; font-size:32px; font-weight:600; color:{color}">
                Monte Carlo Success Probability: {probability:.2f}%
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    # === AVERAGE SIM
    avg_dates, avg_portfolio, avg_withdrawals = simulate_average_simulation_annual(
        user_initial_deposit,
        user_annual_deposit,
        user_deposit_growth_rate,
        user_annual_return_rate,
        user_annual_inflation_rate,
        user_annual_withdrawal_rate,
        user_target_annual_living_cost,
        user_years,
        user_annual_volatility,
        user_start_date,
        user_num_sims,
        user_mode
    )

    # Build a yearly plot
    fig = go.Figure()
    year_indices = range(user_years)
    x_vals = [avg_dates[i] for i in year_indices]

    # Plot portfolio
    fig.add_trace(
        go.Scatter(
            x=x_vals,
            y=avg_portfolio,
            name="Portfolio (Avg)",
            mode='lines+markers',
            line=dict(color='cyan', width=3)
        )
    )

    # Plot withdrawal each year
    fig.add_trace(
        go.Scatter(
            x=x_vals,
            y=avg_withdrawals,
            name="Yearly Withdrawal (Avg)",
            mode='lines+markers',
            line=dict(color='yellow', width=2, dash='dot')
        )
    )

    # Mark the first year we see withdrawals
    first_wd_idx = next((i for i, w in enumerate(avg_withdrawals) if w > 1e-9), None)
    if first_wd_idx is not None:
        x_val = x_vals[first_wd_idx]
        y_val = avg_portfolio[first_wd_idx]
        fig.add_vline(x=x_val, line_width=2, line_dash="dash", line_color="green")
        fig.add_annotation(
            x=x_val,
            y=y_val,
            text="Withdrawal Start (Avg)",
            showarrow=True,
            arrowhead=2,
            ax=0,
            ay=-40,
            font=dict(color="green"),
            arrowcolor="green"
        )

    fig.update_layout(
        title=f"Annual Portfolio & Withdrawals (Mode: {user_mode})",
        xaxis_title="Year Index (Date Shown)",
        yaxis_title="£",
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=40, r=40, t=60, b=40)
    )

    st.plotly_chart(fig, use_container_width=True)

    # Show textual summary
    display_summary_for_average_annual(avg_dates, avg_portfolio, avg_withdrawals)

    # Simple inflation check
    infl_factor = (1 + user_annual_inflation_rate) ** user_years
    st.write(
        f"**Inflation Check:** With {user_annual_inflation_rate * 100:.2f}% annual inflation over {user_years} years, "
        f"£100 today is about £{100 * infl_factor:,.2f} in year {user_years}."
    )

    # Meme break
    display_memes(probability)

if __name__ == "__main__":
    main()