from typing import Annotated

from fastapi import Depends
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import DATABASE_PATH, AVAILABLE_METRICS
from app.models import Base, Metric


engine = create_engine(f'sqlite:///{DATABASE_PATH}', echo=False)
SessionLocal = sessionmaker(bind=engine)


def init_db():
    Base.metadata.create_all(engine)
    seed_metrics()


def seed_metrics():
    '''Seed default metrics if they don't exist.'''
    db = SessionLocal()
    try:
        for metric_data in AVAILABLE_METRICS:
            existing = db.query(Metric).filter(Metric.name == metric_data['name']).first()
            if not existing:
                metric = Metric(**metric_data)
                db.add(metric)
        db.commit()
    finally:
        db.close()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


SessionDep = Annotated[Session, Depends(get_db)]
