from app.schemas.domain import AvailableModel, MissionConstraints


def recommend_model(constraints: MissionConstraints, models: list[AvailableModel]) -> AvailableModel:
    eligible = [
        model
        for model in models
        if constraints.data_residency in model.data_residencies
        and (constraints.cloud_access_allowed or not model.cloud)
        and model.estimated_daily_cost_usd is not None
        and model.estimated_daily_cost_usd <= constraints.daily_budget_usd
    ]
    if not eligible:
        raise ValueError("No registered model satisfies residency, cloud, and budget constraints.")
    eligible.sort(
        key=lambda model: (
            abs((model.reasoning_tier or 3) - constraints.task_complexity),
            model.estimated_daily_cost_usd,
        )
    )
    return eligible[0]