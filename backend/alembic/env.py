from alembic import context
from sqlalchemy import create_engine, pool

from app.core.config import get_settings
from app.db.session import Base
from app.models.entities import Project, Recording  # noqa: F401

from app.models.replay import ReplaySession, ReplayResult  # noqa: F401

from app.models.comparison import Comparison, Difference, ProjectComparisonSettings  # noqa: F401

from app.models.compatibility import CompatibilityAnalysis, CompatibilityFinding, CompatibilityRun, CompatibilityRunItem, ProjectCompatibilityPolicies  # noqa: F401

target_metadata = Base.metadata
url = get_settings().database_url
if context.is_offline_mode():
    context.configure(
        url=url, target_metadata=target_metadata, literal_binds=True, compare_type=True
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = create_engine(url, poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata, compare_type=True
        )
        with context.begin_transaction():
            context.run_migrations()
