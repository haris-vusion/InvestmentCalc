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
BASE_BASIC_RATE_LIMIT   = 50270
BASE_HIGHER_RATE_LIMIT  = 125140

def calc_tax_annual(gross, pa, brt, hrt):
    if gross <= 0:
        return 0.0
    tax = 0.0
    if gross <= pa:
        return 0.0
    basic_portion = max(0, min(gross, brt) - pa)
    higher_portion = max(0, min(gross, hrt) - brt) if gross > brt else 0
    additional_portion = max(0, gross - hrt) if gross > hrt else 0
    tax += basic_portion * 0.20
    tax += higher_portion * 0.40
    tax += additional_portion * 0.45
    return tax

def calc_net_annual(gross, pa, brt, hrt):
    return gross - calc_tax_annual(gross, pa, brt, hrt)

def required_gross_annual_for_net_annual(net_annual, pa, brt, hrt):
    """Binary search to find how much gross is needed to net a certain amount."""
    if net_annual <= 0:
        return 0.0
    low, high = 0.0, 2_000_000.0
    for _ in range(50):
        mid = (low + high) / 2.0
        if calc_net_annual(mid, pa, brt, hrt) < net_annual:
            low = mid
        else:
            high = mid
    return high

def get_tax_brackets_for_year(year, annual_inflation_rate):
    """
    Every 5 years, tax brackets get inflated by (1 + annual_inflation_rate)^5.
    year // 5 => how many 5-year chunks have passed.
    """
    inflation_periods = year // 5
    factor = (1 + annual_inflation_rate) ** (5 * inflation_periods)
    pa  = BASE_PERSONAL_ALLOWANCE * factor
    brt = BASE_BASIC_RATE_LIMIT  * factor
    hrt = BASE_HIGHER_RATE_LIMIT * factor
    return pa, brt, hrt

############################
# 2) SIMULATION LOGIC
############################
def simulate_investment(
    initial_deposit,
    monthly_deposit,
    deposit_growth_rate,
    annual_return_rate,
    annual_inflation_rate,
    annual_withdrawal_rate,    # Not really used now, since we rely on net-living threshold
    target_annual_living_cost, # in today's money
    years,
    annual_volatility,
    start_date
):
    """
    A monthly simulation ensuring we only withdraw if the portfolio can fully pay
    the inflation-adjusted net cost (including tax). Otherwise, 0. Once withdrawals begin,
    we stop deposits.

    Steps each month:
      1) Determine which year we're in => inflation factor for the target living cost.
      2) Compute how much gross is needed to net that monthly fraction (1/12) of the inflated cost.
      3) If portfolio can pay it, withdraw that amount; otherwise 0.
      4) Once we start withdrawing, no more deposits.
    """

    total_months = years * 12
    monthly_mean_return = (1 + annual_return_rate) ** (1/12) - 1
    monthly_std = annual_volatility / (12 ** 0.5)

    portfolio_value = initial_deposit
    start_withdrawal_date = None
    withdrawing = False
    total_withdrawn = 0.0

    dates_list = []
    portfolio_values = []
    withdrawal_values = []

    current_monthly_deposit = monthly_deposit

    for m in range(total_months):
        current_date = start_date + relativedelta(months=m)

        # figure out which year
        current_year = m // 12

        # inflation-adjusted cost for that year
        inflated_annual_cost = target_annual_living_cost * (1 + annual_inflation_rate) ** current_year
        monthly_net_cost = inflated_annual_cost / 12.0

        # how much gross needed for that monthly cost
        pa, brt, hrt = get_tax_brackets_for_year(current_year, annual_inflation_rate)
        gross_needed_annual = required_gross_annual_for_net_annual(inflated_annual_cost, pa, brt, hrt)
        gross_needed_monthly = gross_needed_annual / 12.0

        # see if we can start withdrawing
        if not withdrawing:
            if portfolio_value >= gross_needed_monthly:
                withdrawing = True
                start_withdrawal_date = current_date

        # if not withdrawing, deposit
        if not withdrawing:
            portfolio_value += current_monthly_deposit
            if m > 0:
                current_monthly_deposit *= (1 + deposit_growth_rate)

        # apply random monthly return
        monthly_return = random.gauss(monthly_mean_return, monthly_std)
        portfolio_value *= (1 + monthly_return)

        # if withdrawing, pay the full monthly gross if we can
        if withdrawing:
            if portfolio_value >= gross_needed_monthly:
                withdrawal_amt = gross_needed_monthly
            else:
                withdrawal_amt = 0.0
            portfolio_value -= withdrawal_amt
        else:
            withdrawal_amt = 0.0

        total_withdrawn += withdrawal_amt

        dates_list.append(current_date)
        portfolio_values.append(portfolio_value)
        withdrawal_values.append(withdrawal_amt)

    return dates_list, portfolio_values, withdrawal_values, start_withdrawal_date, total_withdrawn


def simulate_average_simulation(
    initial_deposit,
    monthly_deposit,
    deposit_growth_rate,
    annual_return_rate,
    annual_inflation_rate,
    annual_withdrawal_rate,
    target_annual_living_cost,
    years,
    annual_volatility,
    start_date,
    num_simulations
):
    """
    Runs multiple simulations and returns the average portfolio & withdrawals over time.
    """
    total_months = years * 12
    aggregated_portfolio = [0.0] * total_months
    aggregated_withdrawal = [0.0] * total_months
    dates = None

    for _ in range(num_simulations):
        d, pv, wv, _, _ = simulate_investment(
            initial_deposit,
            monthly_deposit,
            deposit_growth_rate,
            annual_return_rate,
            annual_inflation_rate,
            annual_withdrawal_rate,
            target_annual_living_cost,
            years,
            annual_volatility,
            start_date
        )
        if dates is None:
            dates = d
        for i in range(total_months):
            aggregated_portfolio[i] += pv[i]
            aggregated_withdrawal[i] += wv[i]

    avg_portfolio = [p / num_simulations for p in aggregated_portfolio]
    avg_withdrawal = [w / num_simulations for w in aggregated_withdrawal]
    return dates, avg_portfolio, avg_withdrawal

############################
# 3) PLOTTING & SUMMARIES
############################
def display_summary_for_average(dates, portfolio, withdrawals, start_date):
    """
    Summarizes the average simulation's results, detecting the first time
    (if any) that the average monthly withdrawal goes above zero.
    """
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
        st.write("• The *average* portfolio never reached the threshold to sustain your target living cost.")
        st.write(f"• Final average portfolio value: £{final_portfolio:,.2f}")
        st.write("• Total average withdrawn: £0.00 (No withdrawals were made.)")
    else:
        start_withdraw_date = dates[first_withdraw_idx]
        years_to_withdraw = (start_withdraw_date - start_date).days / 365.25
        st.write(
            f"• Withdrawals (on average) began on **{start_withdraw_date.strftime('%Y-%m-%d')}** "
            f"(~**{years_to_withdraw:.2f} years** into the simulation)."
        )
        st.write(f"• Final average portfolio value: £{final_portfolio:,.2f}")
        st.write(f"• Total average withdrawn: £{total_withdrawn:,.2f}")


##############################
# 4) MONTE CARLO & MEMES
##############################
def run_monte_carlo(
    initial_deposit,
    monthly_deposit,
    deposit_growth_rate,
    annual_return_rate,
    annual_inflation_rate,
    annual_withdrawal_rate,
    target_annual_living_cost,
    years,
    annual_volatility,
    start_date,
    num_simulations
):
    """
    Counts how many simulations both start withdrawals AND end with a positive portfolio balance.
    """
    success_count = 0
    for _ in range(num_simulations):
        _, portfolio_vals, _, start_wd, _ = simulate_investment(
            initial_deposit,
            monthly_deposit,
            deposit_growth_rate,
            annual_return_rate,
            annual_inflation_rate,
            annual_withdrawal_rate,
            target_annual_living_cost,
            years,
            annual_volatility,
            start_date
        )
        if start_wd is not None and portfolio_vals[-1] > 0:
            success_count += 1
    return (success_count / num_simulations) * 100

def display_memes(probability):
    """Show exactly one meme, centered, based on outcome."""
    good_memes_folder = "goodMemes"
    bad_memes_folder = "badMemes"

    if probability >= 50:
        meme_folder = good_memes_folder
        st.markdown("### Congratulations! It's a Good Outcome Meme Break")
    else:
        meme_folder = bad_memes_folder
        st.markdown("### Ouch... It's a Bad Outcome Meme Break")

    try:
        all_files = os.listdir(meme_folder)
        image_files = [f for f in all_files if f.lower().endswith(('.png', '.jpg', '.jpeg', '.gif'))]
        if not image_files:
            st.write("No meme images found in", meme_folder)
            return
        chosen_meme = random.choice(image_files)
        meme_path = os.path.join(meme_folder, chosen_meme)
        col1, col2, col3 = st.columns([1, 2, 1])
        col2.image(meme_path, caption=chosen_meme, width=300)
    except Exception as e:
        st.write("Could not load memes from folder:", meme_folder)
        st.write(e)

##############################
# 5) MAIN APP
##############################
def main():
    st.set_page_config(page_title="Haris' Lods of Emone", layout="wide")

    # Minimal custom CSS
    st.markdown("""
        <style>
        .small-metric {
            text-align: center;
            font-size: 32px;
            font-weight: 600;
            margin-top: 10px;
            margin-bottom: 10px;
        }
        .subtle-box {
            background-color: #1c1c1c;
            border-radius: 8px;
            padding: 15px;
            margin-bottom: 20px;
        }
        .center-text {
            text-align: center;
        }
        </style>
    """, unsafe_allow_html=True)

    st.title("Haris' Lods of Emone Simulator")
    st.write(
        "A sleek, user-focused simulator that factors in a simplified UK tax system, "
        "inflation-adjusted brackets, and monthly deposit growth. Your living cost is treated **post-tax**."
    )

    # Default param dictionary (in PERCENT for rates)
    default_params = {
        "start_date": datetime.today().date(),
        "initial_deposit": 1000,
        "monthly_deposit": 100,
        "annual_inflation_rate": 4.8,   # 4.8% annual
        "deposit_growth_rate": 0.1,     # 0.1% monthly
        "annual_return_rate": 14.8,     # 14.8% annual
        "annual_withdrawal_rate": 4.0,  # 4.0% annual
        "target_annual_living_cost": 30000,
        "years": 20,
        "annual_volatility": 15.0,      # 15% stdev
        "num_simulations": 50
    }

    # === SIDEBAR ===
    st.sidebar.header("Simulation Parameters")
    user_start_date = st.sidebar.date_input(
        "Starting Date",
        value=default_params["start_date"],
        help="When does your simulation begin?"
    )
    user_initial_deposit = st.sidebar.number_input(
        "Initial Deposit (£)",
        min_value=0,
        value=default_params["initial_deposit"],
        step=500,
        help="How much money do you start with?"
    )
    user_monthly_deposit = st.sidebar.number_input(
        "Monthly Deposit (£)",
        min_value=0,
        value=default_params["monthly_deposit"],
        step=50,
        help="How much you contribute each month initially."
    )
    user_annual_inflation_rate = st.sidebar.slider(
        "Annual Inflation Rate (%)",
        0.0, 7.0,
        default_params["annual_inflation_rate"],
        0.2,
        help="Expected annual inflation, also used to adjust tax brackets every 5 years."
    )
    user_deposit_growth_rate = st.sidebar.slider(
        "Monthly Deposit Growth Rate (%)",
        0.0, 2.0,
        default_params["deposit_growth_rate"],
        0.1,
        help="Rate at which your monthly deposit grows each month."
    )
    user_annual_return_rate = st.sidebar.slider(
        "Annual Return Rate (%)",
        0.0, 20.0,
        default_params["annual_return_rate"],
        0.2,
        help="Projected average annual return on your portfolio."
    )
    user_annual_withdrawal_rate = st.sidebar.slider(
        "Annual Withdrawal Rate (%)",
        0.0, 20.0,
        default_params["annual_withdrawal_rate"],
        0.5,
        help="Percentage of the portfolio you withdraw annually once you start living off it."
    )
    user_target_annual_living_cost = st.sidebar.number_input(
        "Target Net Annual Living Cost (£)",
        min_value=0,
        value=default_params["target_annual_living_cost"],
        step=1000,
        help="How much you want to spend (post-tax) each year."
    )
    user_years = st.sidebar.slider(
        "Number of Years to Simulate",
        1, 100,
        default_params["years"],
        1,
        help="How many years does this simulation run?"
    )
    user_annual_volatility = st.sidebar.slider(
        "Annual Volatility (%)",
        0.0, 30.0,
        default_params["annual_volatility"],
        0.2,
        help="Market volatility (standard deviation). Higher means bigger swings."
    )
    user_num_simulations = st.sidebar.number_input(
        "Monte Carlo Simulations",
        min_value=10,
        value=default_params["num_simulations"],
        step=10,
        help="Number of runs for both the average curve and success probability."
    )

    # Convert user params from % => decimal
    user_annual_inflation_rate   /= 100.0
    user_deposit_growth_rate     /= 100.0
    user_annual_return_rate      /= 100.0
    user_annual_withdrawal_rate  /= 100.0
    user_annual_volatility       /= 100.0

    # Float check
    def floats_match(a, b):
        return abs(a - b) < 1e-9

    # If unchanged, just prompt
    unchanged = (
        (user_start_date == default_params["start_date"]) and
        (user_initial_deposit == default_params["initial_deposit"]) and
        (user_monthly_deposit == default_params["monthly_deposit"]) and
        floats_match(user_annual_inflation_rate*100.0, default_params["annual_inflation_rate"]) and
        floats_match(user_deposit_growth_rate*100.0, default_params["deposit_growth_rate"]) and
        floats_match(user_annual_return_rate*100.0, default_params["annual_return_rate"]) and
        floats_match(user_annual_withdrawal_rate*100.0, default_params["annual_withdrawal_rate"]) and
        (user_target_annual_living_cost == default_params["target_annual_living_cost"]) and
        (user_years == default_params["years"]) and
        floats_match(user_annual_volatility*100.0, default_params["annual_volatility"]) and
        (user_num_simulations == default_params["num_simulations"])
    )

    if unchanged:
        st.markdown("## Welcome!")
        st.write("Adjust the parameters in the sidebar to begin the auto-run simulation.\n\n"
                 "You'll see the results here as soon as you change something!")
        return

    # Monte Carlo success
    probability = run_monte_carlo(
        user_initial_deposit,
        user_monthly_deposit,
        user_deposit_growth_rate,
        user_annual_return_rate,
        user_annual_inflation_rate,
        user_annual_withdrawal_rate,
        user_target_annual_living_cost,
        user_years,
        user_annual_volatility,
        user_start_date,
        int(user_num_simulations)
    )

    color = "#2ecc71" if probability >= 50 else "#e74c3c"
    st.markdown(
        f"<div class='subtle-box'><div class='small-metric' style='color:{color}'>"
        f"Monte Carlo Success Probability: {probability:.2f}%"
        f"</div></div>",
        unsafe_allow_html=True
    )

    # Average simulation
    avg_dates, avg_portfolio, avg_withdrawals = simulate_average_simulation(
        user_initial_deposit,
        user_monthly_deposit,
        user_deposit_growth_rate,
        user_annual_return_rate,
        user_annual_inflation_rate,
        user_annual_withdrawal_rate,
        user_target_annual_living_cost,
        user_years,
        user_annual_volatility,
        user_start_date,
        int(user_num_simulations)
    )

    # Build a yearly chart from monthly average data
    fig = go.Figure()

    total_months = len(avg_dates)
    year_end_dates = []
    year_end_portfolio = []
    yearly_withdrawals = []

    for year_idx in range(user_years):
        end_idx = (year_idx+1)*12 - 1
        if end_idx >= total_months:
            break
        year_end_dates.append(avg_dates[end_idx])
        year_end_portfolio.append(avg_portfolio[end_idx])

        # sum monthly avg withdrawals for that year
        start_of_year = year_idx * 12
        end_of_year = min((year_idx+1)*12, total_months)
        sum_wd = sum(avg_withdrawals[start_of_year:end_of_year])
        yearly_withdrawals.append(sum_wd)

    # Plot yearly portfolio
    fig.add_trace(
        go.Scatter(
            x=year_end_dates,
            y=year_end_portfolio,
            mode='lines+markers',
            line=dict(color='#17becf', width=3),
            marker=dict(size=8),
            name='Year-End Portfolio (Avg)',
            hovertemplate="Year End: %{x|%Y-%m-%d}<br>Portfolio: £%{y:,.2f}<extra></extra>"
        )
    )

    # Plot yearly actual withdrawals
    fig.add_trace(
        go.Scatter(
            x=year_end_dates,
            y=yearly_withdrawals,
            mode='lines+markers',
            line=dict(color='yellow', width=2, dash='dot'),
            marker=dict(size=8),
            name='Yearly Actual Withdrawal (Avg)',
            hovertemplate=(
                "Year End: %{x|%Y-%m-%d}<br>"
                "Actual Withdrawn This Year: £%{y:,.2f}<extra></extra>"
            )
        )
    )

    # Add vertical line if we started withdrawing
    first_wd_year_idx = next((i for i, w in enumerate(yearly_withdrawals) if w > 1e-9), None)
    if first_wd_year_idx is not None:
        x_val = year_end_dates[first_wd_year_idx]
        fig.add_vline(x=x_val, line_width=2, line_dash="dash", line_color="green")
        fig.add_annotation(
            x=x_val,
            y=year_end_portfolio[first_wd_year_idx],
            text="Withdrawal Start (Avg)",
            showarrow=True,
            arrowhead=2,
            ax=0,
            ay=-40,
            font=dict(color="green"),
            arrowcolor="green"
        )

    # Milestones on monthly data
    milestone_x = []
    milestone_y = []
    milestone_text = []
    milestones = [10000, 100000, 250000, 500000, 1000000, 10000000, 50000000, 100000000, 250000000, 500000000]
    for milestone in milestones:
        idx = next((m for m, val in enumerate(avg_portfolio) if val >= milestone), None)
        if idx is not None:
            milestone_x.append(avg_dates[idx])
            milestone_y.append(avg_portfolio[idx])
            if milestone == milestones[-1]:
                milestone_text.append(f"£{milestone/1e6:.0f}m – Billionaire!")
            else:
                if milestone < 1_000_000:
                    milestone_text.append(f"£{milestone/1000:.0f}k")
                else:
                    milestone_text.append(f"£{milestone/1e6:.0f}m")

    fig.add_trace(
        go.Scatter(
            x=milestone_x,
            y=milestone_y,
            mode="markers+text",
            text=milestone_text,
            textposition="top center",
            marker=dict(color="green", size=10, symbol="diamond"),
            name="Milestones",
            hoverinfo="none"
        )
    )

    fig.update_yaxes(tickformat=",.2f")
    fig.update_layout(
        title="Portfolio Growth & Withdrawals Over Time (Average Only, Yearly)",
        xaxis_title="Date",
        yaxis_title="£",
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=40, r=40, t=60, b=40)
    )

    st.plotly_chart(fig, use_container_width=True)

    # Summary
    display_summary_for_average(
        avg_dates,
        avg_portfolio,
        avg_withdrawals,
        user_start_date
    )

    # Inflation check
    inflation_factor = (1 + user_annual_inflation_rate) ** user_years
    st.write(
        f"**Inflation Check:** With {user_annual_inflation_rate*100:.2f}% annual inflation over {user_years} years, "
        f"£100 **today** will be roughly £{100 * inflation_factor:.2f} in year {user_years}."
    )

    display_memes(probability)

if __name__ == "__main__":
    main()
