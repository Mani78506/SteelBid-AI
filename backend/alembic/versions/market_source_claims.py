"""durable market source claims

Revision ID: market_source_claims
Revises: market_source_provider_cfg
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision="market_source_claims"; down_revision="market_source_provider_cfg"; branch_labels=None; depends_on=None
def upgrade():
 op.create_table("market_source_claims",sa.Column("id",postgresql.UUID(as_uuid=True),primary_key=True),sa.Column("source_id",postgresql.UUID(as_uuid=True),sa.ForeignKey("market_sources.id",ondelete="CASCADE"),nullable=False),sa.Column("claim_token",sa.String(64),nullable=False,unique=True),sa.Column("claim_owner",sa.String(128),nullable=False),sa.Column("claimed_at",sa.DateTime(timezone=True),nullable=False),sa.Column("expires_at",sa.DateTime(timezone=True),nullable=False),sa.Column("created_at",sa.DateTime(timezone=True),server_default=sa.func.now()),sa.Column("updated_at",sa.DateTime(timezone=True),server_default=sa.func.now()),sa.UniqueConstraint("source_id",name="uq_market_source_claim_source")); op.create_index("ix_market_source_claims_expires_at","market_source_claims",["expires_at"])
def downgrade(): op.drop_table("market_source_claims")
