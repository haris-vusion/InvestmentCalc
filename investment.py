import streamlit as st
import plotly.graph_objects as go
import random
import math
from datetime import datetime
from dateutil.relativedelta import relativedelta
import os

def simulate_investment(
    initial_deposit,
    monthly_deposit,
    annual_return_rate,
    annual_inflation_rate,
    annual_withdrawal_rate,
    target_annual_living_cost,
    years,
    annual_volatility,
    start_date
):
    total_months = years * 12
    monthly_mean_return = (1 + annual_return_rate) ** (1/12) - 1
    monthly_std = annual_volatility / (12 ** 0.5)
    monthly_inflation_rate = (1 + annual_inflation_rate) ** (1/12) - 1
    initial_monthly_cost = target_annual_living_cost / 12.0

    portfolio_value = initial_deposit
    start_withdrawal_date = None
    withdrawing = False
    total_withdrawn = 0.0

    dates_list = []
    portfolio_values = []
    withdrawal_values = []
    monthly_costs = []

    for month in range(total_months):
        current_date = start_date + relativedelta(months=+month)

        if month == 0:
            this_month_cost = initial_monthly_cost
        else:
            this_month_cost = monthly_costs[-1] * (1 + monthly_inflation_rate)

        required_portfolio = (this_month_cost * 12) / annual_withdrawal_rate
        if not withdrawing and portfolio_value >= required_portfolio:
            withdrawing = True
            start_withdrawal_date = current_date

        portfolio_value += monthly_deposit
        current_month_return = random.gauss(monthly_mean_return, monthly_std)
        portfolio_value *= (1 + current_month_return)

        if withdrawing:
            withdrawal_amt = min(this_month_cost, portfolio_value)
            portfolio_value -= withdrawal_amt
        else:
            withdrawal_amt = 0.0

        total_withdrawn += withdrawal_amt

        dates_list.append(current_date)
        portfolio_values.append(portfolio_value)
        withdrawal_values.append(withdrawal_amt)
        monthly_costs.append(this_month_cost)

    return dates_list, portfolio_values, withdrawal_values, start_withdrawal_date, total_withdrawn

def create_plot(dates, portfolio_values, withdrawal_values, start_withdrawal_date):
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=dates,
            y=portfolio_values,
            mode='lines',
            line=dict(color='blue', width=2),
            name='Portfolio Value (£)'
        )
    )
    fig.add_trace(
        go.Scatter(
            x=dates,
            y=withdrawal_values,
            mode='lines',
            line=dict(color='red', width=2, dash='dot'),
            name='Monthly Withdrawal (£)'
        )
    )
    if start_withdrawal_date is not None:
        fig.add_vline(
            x=start_withdrawal_date,
            line_width=2,
            line_color="green"
        )
        fig.add_annotation(
            x=start_withdrawal_date,
            y=1,
            xref="x",
            yref="paper",
            text="Withdrawals Begin",
            showarrow=True,
            arrowhead=1,
            ax=0,
            ay=-40
        )
    fig.update_layout(
        title="Portfolio Growth & Withdrawals Over Time (with Random Volatility)",
        xaxis_title="Date",
        yaxis_title="£",
        hovermode="x unified",
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1
        )
    )
    return fig

def display_summary(start_withdrawal_date, total_withdrawn, portfolio_values, start_date):
    st.subheader("Summary")
    if start_withdrawal_date is None:
        st.write("• The portfolio never reached the threshold to sustain your target living cost. Ouch!")
        st.write(f"• Final portfolio value: £{portfolio_values[-1]:,.2f}")
        st.write("• Total withdrawn: £0.00 (No withdrawals were made.)")
    else:
        years_to_withdraw = (start_withdrawal_date - start_date).days / 365.25
        st.write(
            f"• Started withdrawing on **{start_withdrawal_date.strftime('%Y-%m-%d')}** "
            f"(after about **{years_to_withdraw:.2f} years**)."
        )
        st.write(f"• Final portfolio value: £{portfolio_values[-1]:,.2f}")
        st.write(f"• Total withdrawn: £{total_withdrawn:,.2f}")

def run_monte_carlo(
    initial_deposit,
    monthly_deposit,
    annual_return_rate,
    annual_inflation_rate,
    annual_withdrawal_rate,
    target_annual_living_cost,
    years,
    annual_volatility,
    start_date,
    num_simulations
):
    success_count = 0
    for _ in range(num_simulations):
        _, portfolio_values, _, start_withdrawal_date, _ = simulate_investment(
            initial_deposit,
            monthly_deposit,
            annual_return_rate,
            annual_inflation_rate,
            annual_withdrawal_rate,
            target_annual_living_cost,
            years,
            annual_volatility,
            start_date
        )
        if start_withdrawal_date is not None and portfolio_values[-1] > 0:
            success_count += 1
    success_probability = (success_count / num_simulations) * 100
    return success_probability

def display_memes(probability):
    """
    Display exactly ONE meme, centered, based on whether the outcome is 'good' or 'bad.'
    We'll say 'good' if probability >= 50, else 'bad'.
    """
    good_memes_folder = "goodMemes"  # Make sure these folders exist and have images
    bad_memes_folder = "badMemes"

    if probability >= 50:
        meme_folder = good_memes_folder
        st.markdown("### Congratulations, you can buy more useless stuff!")
    else:
        meme_folder = bad_memes_folder
        st.markdown("### You're Screwed...")

    try:
        all_files = os.listdir(meme_folder)
        image_files = [f for f in all_files if f.lower().endswith(('.png', '.jpg', '.jpeg', '.gif'))]
        if not image_files:
            st.write("No meme images found in", meme_folder)
            return

        # Pick exactly 1 random meme
        chosen_meme = random.choice(image_files)
        meme_path = os.path.join(meme_folder, chosen_meme)

        # Create 3 columns and display the image in the middle column
        col1, col2, col3 = st.columns([1, 2, 1])
        col2.image(meme_path, caption=chosen_meme, width=300)

    except Exception as e:
        st.write("Could not load memes from folder:", meme_folder)
        st.write(e)

def main():
    st.title("Haris' Lods of Emone Simulator")
    st.write("Simulator to buy more cars and dumb shit")
    st.info("On mobile, tap the menu in the top-left corner to see the Simulation Parameters.")

    st.sidebar.header("Simulation Parameters")
    start_date = st.sidebar.date_input("Starting Date", value=datetime.today())
    initial_deposit = st.sidebar.number_input("Initial Deposit (£)", min_value=0, value=1000, step=500)
    monthly_deposit = st.sidebar.number_input("Monthly Deposit (£) (20% of Income)", min_value=0, value=100, step=50)
    annual_return_rate = st.sidebar.slider(
        "Annual Return Rate (%) (14.8% NASDAQ'S Average)",
        0.0, 20.0, 14.8, 0.2
    ) / 100.0
    annual_inflation_rate = st.sidebar.slider(
        "Annual Inflation Rate (%) (4.8% Average)",
        0.0, 7.0, 4.8, 0.2
    ) / 100.0
    annual_withdrawal_rate = st.sidebar.slider(
        "Annual Withdrawal Rate (%) (4% Recommended)",
        0.0, 20.0, 4.0, 0.5
    ) / 100.0
    target_annual_living_cost = st.sidebar.number_input(
        "Target Annual Living Cost (£)",
        min_value=0,
        value=30000,
        step=1000
    )
    years = st.sidebar.slider("Number of Years to Simulate", 1, 40, 20, 1)
    annual_volatility = st.sidebar.slider("Annual Volatility (%)", 0.0, 50.0, 15.0, 0.5) / 100.0
    num_simulations = st.sidebar.number_input("Monte Carlo Simulations", min_value=100, value=1000, step=100)

    # Run simulation automatically
    dates, portfolio_values, withdrawal_values, start_withdrawal_date, total_withdrawn = simulate_investment(
        initial_deposit,
        monthly_deposit,
        annual_return_rate,
        annual_inflation_rate,
        annual_withdrawal_rate,
        target_annual_living_cost,
        years,
        annual_volatility,
        start_date
    )
    fig = create_plot(dates, portfolio_values, withdrawal_values, start_withdrawal_date)
    st.plotly_chart(fig, use_container_width=True)
    display_summary(start_withdrawal_date, total_withdrawn, portfolio_values, start_date)

    st.subheader("Monte Carlo Success Probability")
    probability = run_monte_carlo(
        initial_deposit,
        monthly_deposit,
        annual_return_rate,
        annual_inflation_rate,
        annual_withdrawal_rate,
        target_annual_living_cost,
        years,
        annual_volatility,
        start_date,
        int(num_simulations)
    )
    st.write(
        f"Based on {num_simulations} simulations, the probability of this actually working "
        f"(starting withdrawals and ending with a positive balance) is **{probability:.2f}%**."
    )

    # Show exactly one good/bad meme, centered
    display_memes(probability)

if __name__ == "__main__":
    main()
