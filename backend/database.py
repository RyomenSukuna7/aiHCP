import os
import uuid
from datetime import datetime

from dotenv import load_dotenv
from sqlalchemy import create_engine, Column, String, Text, DateTime, JSON
from sqlalchemy.orm import declarative_base, sessionmaker

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./hcp_crm.db")

# SQLite needs check_same_thread=False; the connect_args are ignored by other DBs
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, pool_pre_ping=True, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


class Interaction(Base):
    """A single logged HCP interaction. Mirrors the fields on the Log
    Interaction screen so the form and the chat agent read/write the
    same record."""

    __tablename__ = "interactions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    hcp_name = Column(String(255))
    interaction_type = Column(String(50), default="Meeting")  # Meeting/Call/Email/Conference
    date = Column(String(20))
    time = Column(String(10))
    attendees = Column(Text)  # comma separated
    topics_discussed = Column(Text)
    materials_shared = Column(JSON, default=list)
    samples_distributed = Column(JSON, default=list)
    sentiment = Column(String(20), default="Neutral")  # Positive/Neutral/Negative
    outcomes = Column(Text)
    follow_up_actions = Column(JSON, default=list)
    ai_suggested_followups = Column(JSON, default=list)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class MaterialSample(Base):
    """Mock catalogue that the search_materials_and_samples tool queries
    against, e.g. brochures, leave-behinds, Phase III PDFs, drug samples."""

    __tablename__ = "materials_samples"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255))
    kind = Column(String(20))  # "material" or "sample"
    tags = Column(String(255))  # comma separated keywords for retrieval


def init_db():
    Base.metadata.create_all(bind=engine)
    # seed a small mock catalogue if empty
    with SessionLocal() as db:
        if db.query(MaterialSample).count() == 0:
            seed = [
                MaterialSample(id=str(uuid.uuid4()), name="OncoBoost Phase III PDF",
                                kind="material", tags="oncoboost,phase3,efficacy,oncology"),
                MaterialSample(id=str(uuid.uuid4()), name="Product X Efficacy Brochure",
                                kind="material", tags="product x,brochure,efficacy"),
                MaterialSample(id=str(uuid.uuid4()), name="CardioGuard Dosing Card",
                                kind="material", tags="cardioguard,dosing,cardiology"),
                MaterialSample(id=str(uuid.uuid4()), name="OncoBoost 50mg Sample Pack",
                                kind="sample", tags="oncoboost,sample,oncology"),
                MaterialSample(id=str(uuid.uuid4()), name="CardioGuard 10mg Sample",
                                kind="sample", tags="cardioguard,sample,cardiology"),
            ]
            db.add_all(seed)
            db.commit()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
