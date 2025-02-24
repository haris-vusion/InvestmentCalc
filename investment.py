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
    annual_withdrawal_rate,    # Not really used now, since we rely on the net-living threshold
    target_annual_living_cost, # In today's money
    years,
    annual_volatility,
    start_date
):
    """
    Monthly simulation ensuring we only withdraw enough to net the inflation-adjusted cost.
    If the portfolio can't sustain it, we withdraw 0.
    Once withdrawals begin, we stop depositing.

    target_annual_living_cost = e.g., 30000 in today's money
    Each year t => inflated_annual_cost = 30000 * (1+inflation_rate)^t
    Then we check if the portfolio >= the "gross needed / annual_withdrawal_rate"?
    Actually, we don't even need annual_withdrawal_rate if we do direct net-living logic:

    We do:
      - If portfolio is big enough to fund that monthly net cost, we withdraw it (grossed up for tax).
      - Otherwise, 0.
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
    withdrawal_values = []  # This is the GROSS withdrawal each month

    current_monthly_deposit = monthly_deposit

    for m in range(total_months):
        current_date = start_date + relativedelta(months=m)

        # Determine which year we're in to inflate the cost
        current_year = m // 12
        # e.g., if m=0..11 => year 0, 12..23 => year 1, etc.

        # The "net cost" in that year, inflation-adjusted
        inflated_annual_cost = target_annual_living_cost * (1 + annual_inflation_rate) ** current_year
        monthly_net_cost = inflated_annual_cost / 12.0

        # Check if we can sustain it. That requires us to find how much GROSS is needed to net monthly_net_cost.
        pa, brt, hrt = get_tax_brackets_for_year(current_year, annual_inflation_rate)
        gross_needed_per_month = required_gross_annual_for_net_annual(inflated_annual_cost, pa, brt, hrt) / 12.0

        # If portfolio >= gross_needed_per_month * 12 for the year?
        # Actually, let's do monthly check:
        # If portfolio can handle gross_needed_per_month, we withdraw it, else 0.
        # But we also want a single "once I'm big enough, I retire" approach:
        # We'll do a simple approach: if portfolio >= gross_needed_per_month, we withdraw.
        # Once we start withdrawing, we also stop deposits.

        if not withdrawing:
            # See if we can start withdrawing
            if portfolio_value >= gross_needed_per_month:
                withdrawing = True
                start_withdrawal_date = current_date

        # If not withdrawing, deposit
        if not withdrawing:
            portfolio_value += current_monthly_deposit
            # Grow deposit for next month
            if m > 0:
                current_monthly_deposit *= (1 + deposit_growth_rate)

        # Apply monthly return
        current_month_return = random.gauss(monthly_mean_return, monthly_std)
        portfolio_value *= (1 + current_month_return)

        # If withdrawing, see if we can pay the entire monthly_net_cost
        if withdrawing:
            if portfolio_value >= gross_needed_per_month:
                # We'll withdraw exactly what's needed to net monthly_net_cost
                # monthly_net_cost is e.g. 2500 if 30k => 12
                # Let's re-check the tax needed for just that monthly cost:
                # We'll do the same approach:
                #   gross for monthly_net_cost => required_gross_annual_for_net_annual(monthly_net_cost*12)/12
                # But we already computed it: 'gross_needed_per_month'
                withdrawal_amt = min(gross_needed_per_month, portfolio_value)
            else:
                # Can't sustain it => withdraw 0
                withdrawal_amt = 0.0

            portfolio_value -= withdrawal_amt
        else:
            withdrawal_amt = 0.0

        total_withdrawn += withdrawal_amt

        # Record
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

    # Find first month index where average withdrawal is non-zero
    first_withdraw_idx = None
    for i, w in enumerate(withdrawals):
        if w > 1e-9:  # or just w > 0 if you prefer
            first_withdraw_idx = i
            break

    total_withdrawn = sum(withdrawals)
    final_portfolio = portfolio[-1]

    st.subheader("Summary (Average Simulation)")

    if first_withdraw_idx is None:
        # Never withdrew in the average scenario
        st.write("• The *average* portfolio never reached the threshold to sustain your target living cost.")
        st.write(f"• Final average portfolio value: £{final_portfolio:,.2f}")
        st.write("• Total average withdrawn: £0.00 (No withdrawals were made.)")
    else:
        # Found a withdrawal start
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
        _, portfolio_vals, _, start_withdrawal_date, _ = simulate_investment(
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
        # "Success" if it eventually started withdrawing AND had > 0 left at the end
        if start_withdrawal_date is not None and portfolio_vals[-1] > 0:
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
        "annual_inflation_rate": 4.8,   # means 4.8% annual
        "deposit_growth_rate": 0.1,     # means 0.1% monthly in the slider
        "annual_return_rate": 14.8,     # means 14.8% annual
        "annual_withdrawal_rate": 4.0,  # means 4.0% annual
        "target_annual_living_cost": 30000,
        "years": 20,
        "annual_volatility": 15.0,      # means 15% standard deviation
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

    # === Convert user params from % => decimal where needed ===
    user_annual_inflation_rate   /= 100.0  # e.g., 4.8 => 0.048
    user_deposit_growth_rate     /= 100.0  # e.g., 0.1 => 0.001
    user_annual_return_rate      /= 100.0  # e.g., 14.8 => 0.148
    user_annual_withdrawal_rate  /= 100.0  # e.g., 4.0 => 0.04
    user_annual_volatility       /= 100.0  # e.g., 15.0 => 0.15

    # Quick function to check float equality
    def floats_match(a, b):
        return abs(a - b) < 1e-9

    # We'll consider them "unchanged" if all match exactly (within float tolerance).
    unchanged = (
        (user_start_date == default_params["start_date"]) and
        (user_initial_deposit == default_params["initial_deposit"]) and
        (user_monthly_deposit == default_params["monthly_deposit"]) and
        floats_match(user_annual_inflation_rate * 100.0, default_params["annual_inflation_rate"]) and
        floats_match(user_deposit_growth_rate * 100.0, default_params["deposit_growth_rate"]) and
        floats_match(user_annual_return_rate * 100.0, default_params["annual_return_rate"]) and
        floats_match(user_annual_withdrawal_rate * 100.0, default_params["annual_withdrawal_rate"]) and
        (user_target_annual_living_cost == default_params["target_annual_living_cost"]) and
        (user_years == default_params["years"]) and
        floats_match(user_annual_volatility * 100.0, default_params["annual_volatility"]) and
        (user_num_simulations == default_params["num_simulations"])
    )

    if unchanged:
        st.markdown("## Welcome!")
        st.write("Adjust the parameters in the sidebar to begin the auto-run simulation.\n\n"
                 "You'll see the results here as soon as you change something!")
        return

    # === Monte Carlo success probability ===
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

    # === AVERAGE SIMULATION ONLY ===
    # This returns monthly data for the average run
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

    # --- CREATE FIGURE ---
    fig = go.Figure()

    # 1) Convert monthly average data -> Yearly data
    #    We'll sample at end of each year for the portfolio,
    #    and sum the monthly withdrawals for that year to get a "yearly actual withdrawal."
    total_months = len(avg_dates)  # should be user_years * 12
    year_end_dates = []
    year_end_portfolio = []
    yearly_actual_withdrawals = []  # sum of that year's monthly average withdrawals

    for year_idx in range(user_years):
        # End-of-year month index
        end_month_idx = (year_idx + 1) * 12 - 1
        if end_month_idx >= total_months:
            break

        # Portfolio at year end
        p = avg_portfolio[end_month_idx]
        year_end_portfolio.append(p)

        # Date at year end
        year_end_dates.append(avg_dates[end_month_idx])

        # Sum the monthly average withdrawals for that entire year
        start_of_year_idx = year_idx * 12
        # e.g., if year_idx=0 => months 0..11
        #       if year_idx=1 => months 12..23
        # and so on
        # Make sure we don't go out of range:
        end_of_year_idx = min((year_idx + 1) * 12, total_months)
        yearly_withdraw_sum = sum(avg_withdrawals[start_of_year_idx:end_of_year_idx])
        yearly_actual_withdrawals.append(yearly_withdraw_sum)

    # 2) Also compute a "Potential Yearly Withdrawal" line
    #    i.e., a 4% rule style figure at year end: portfolio * annual_withdrawal_rate
    #    plus an inflation-adjusted version
    #    So each point's customdata = [nominal_yearly, adjusted_yearly]
    year_customdata = []
    for i, p in enumerate(year_end_portfolio):
        # Nominal 4% rule style
        nominal = p * user_annual_withdrawal_rate

        # Adjust for partial inflation: (1 + inflation)^year
        # i is the 0-based index, but the actual "year" is i+1
        factor = (1 + user_annual_inflation_rate) ** (i + 1)
        adjusted = nominal / factor

        year_customdata.append([nominal, adjusted])

    # 3) Add a trace for "Year-End Portfolio + Potential Yearly Withdrawal"
    fig.add_trace(
        go.Scatter(
            x=year_end_dates,
            y=year_end_portfolio,
            mode='markers+lines',
            line=dict(color='#17becf', width=3),
            marker=dict(size=8),
            name='Yearly Portfolio (Potential Withdrawal)',
            customdata=year_customdata,
            hovertemplate=(
                "Year End: %{x|%Y-%m-%d}<br>"
                "Portfolio: £%{y:,.2f}<br>"
                "Potential Yearly Withdrawal: £%{customdata[0]:,.2f} "
                "(adj. £%{customdata[1]:,.2f})<br>"
                "<extra></extra>"
            )
        )
    )

    # 4) Add a trace for "Yearly Actual Withdrawals" from the average scenario
    fig.add_trace(
        go.Scatter(
            x=year_end_dates,
            y=yearly_actual_withdrawals,
            mode='markers+lines',
            line=dict(color='yellow', width=2, dash='dot'),
            marker=dict(size=8),
            name='Yearly Actual Withdrawal (Avg)',
            hovertemplate=(
                "Year End: %{x|%Y-%m-%d}<br>"
                "Actual Withdrawal This Year: £%{y:,.2f}<br>"
                "<extra></extra>"
            )
        )
    )

    # 5) We also want to place a vertical line when the AVERAGE scenario first starts withdrawing
    #    i.e., the first year that had > 0 actual withdrawals
    first_withdraw_year_idx = next((i for i, w in enumerate(yearly_actual_withdrawals) if w > 1e-9), None)
    if first_withdraw_year_idx is not None:
        x_value = year_end_dates[first_withdraw_year_idx]
        fig.add_vline(x=x_value, line_width=2, line_dash="dash", line_color="green")
        fig.add_annotation(
            x=x_value,
            y=year_end_portfolio[first_withdraw_year_idx],
            text="Withdrawal Start (Avg)",
            showarrow=True,
            arrowhead=2,
            ax=0,
            ay=-40,
            font=dict(color="green"),
            arrowcolor="green"
        )

    # 6) Milestone markers on the average monthly portfolio
    #    (We keep monthly for a smoother milestone detection.)
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
                    milestone_text.append(f"£{milestone/1_000:.0f}k")
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

    # 7) Final figure layout
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

    # === SUMMARY (for average scenario) ===
    # This still uses monthly data for the summary, which is fine.
    # If you prefer a purely yearly approach, you could adapt display_summary_for_average
    # to use the year-end data. For now, let's keep it:
    display_summary_for_average(
        avg_dates,
        avg_portfolio,
        avg_withdrawals,
        user_start_date
    )

    # === INFLATION EQUIVALENCE NOTE ===
    inflation_factor = (1 + user_annual_inflation_rate) ** user_years
    st.write(
        f"**Inflation Check:** With {user_annual_inflation_rate*100:.2f}% annual inflation over {user_years} years, "
        f"£100 **today** will be roughly £{100 * inflation_factor:.2f} in year {user_years}."
    )

    # === Meme time ===
    display_memes(probability)

if __name__ == "__main__":
    main()