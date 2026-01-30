from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    '''Base class for all models.'''
    pass


class Metric(Base):
    '''
    Represents an available processing metric (e.g., grayscale, kerning).
    Metrics are registered in the database and can be enabled/disabled.
    '''

    __tablename__ = 'metrics'

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    # Relationships
    font_metrics: Mapped[list['FontMetric']] = relationship('FontMetric', back_populates='metric')

    def serialize(self) -> dict:
        return {
            'id': self.id,
            'name': self.name,
            'display_name': self.display_name,
            'description': self.description,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class Typeface(Base):
    '''
    Represents a typeface (font family, e.g., "OPPO Sans 4.0").
    A typeface can have multiple fonts (e.g., Regular, Bold, Light).
    '''

    __tablename__ = 'typefaces'

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    # display_name: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    # Relationships
    fonts: Mapped[list['Font']] = relationship('Font', back_populates='typeface', cascade='all, delete-orphan')

    def serialize(self, include_fonts: bool = False) -> dict:
        result = {
            'id': self.id,
            'name': self.name,
            'font_count': len(self.fonts) if self.fonts else 0,
        }
        if include_fonts:
            result['fonts'] = [f.serialize() for f in self.fonts]
        return result


class Font(Base):
    '''
    Represents an individual font file within a typeface.
    Each font can have multiple computed metrics.
    '''

    __tablename__ = 'fonts'

    id: Mapped[int] = mapped_column(primary_key=True)
    typeface_id: Mapped[Optional[int]] = mapped_column(ForeignKey('typefaces.id', ondelete='SET NULL'), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=True)
    subfamily: Mapped[str] = mapped_column(String(255), nullable=True)
    version: Mapped[str] = mapped_column(String(20), nullable=True)
    postscript_name: Mapped[str] = mapped_column(String(255), nullable=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    checksum: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)  # SHA-256 hex

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    # Relationships
    typeface: Mapped[Optional['Typeface']] = relationship('Typeface', back_populates='fonts')
    jobs: Mapped[list['Job']] = relationship('Job', back_populates='font')
    font_metrics: Mapped[list['FontMetric']] = relationship(
        'FontMetric', back_populates='font', cascade='all, delete-orphan'
    )

    def serialize(self, include_metrics: bool = False) -> dict:
        result = {
            'id': self.id,
            'typeface': self.typeface.serialize() if self.typeface else None,
            'name': self.name,
            'subfamily': self.subfamily,
            'version': self.version,
            'postscript_name': self.postscript_name,
        }
        if include_metrics:
            result['computed_metrics'] = [fm.serialize() for fm in self.font_metrics]
        return result

    @property
    def computed_metric_names(self) -> list[str]:
        '''List of metric names that have been computed for this font.'''
        return [fm.metric.name for fm in self.font_metrics if fm.metric]


class FontMetric(Base):
    '''
    Association table linking fonts to their computed metrics.
    Tracks which metrics have been calculated for each font.
    '''

    __tablename__ = 'font_metrics'
    __table_args__ = (UniqueConstraint('font_id', 'metric_id', name='uq_font_metric'),)

    id: Mapped[int] = mapped_column(primary_key=True)
    font_id: Mapped[int] = mapped_column(ForeignKey('fonts.id', ondelete='CASCADE'), nullable=False, index=True)
    metric_id: Mapped[int] = mapped_column(ForeignKey('metrics.id', ondelete='CASCADE'), nullable=False, index=True)
    job_id: Mapped[Optional[str]] = mapped_column(ForeignKey('jobs.id', ondelete='SET NULL'), nullable=True)
    data_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)  # Path to JSONL
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    # Relationships
    font: Mapped['Font'] = relationship('Font', back_populates='font_metrics')
    metric: Mapped['Metric'] = relationship('Metric', back_populates='font_metrics')
    job: Mapped[Optional['Job']] = relationship('Job', back_populates='computed_metrics')

    def serialize(self) -> dict:
        return {
            'id': self.id,
            'font_id': self.font_id,
            'metric': self.metric.serialize() if self.metric else None,
            'job_id': self.job_id,
            # 'data_path': self.data_path,
        }


class Job(Base):
    '''
    Represents a font processing job.
    Each job processes one font with one or more requested metrics.
    '''

    __tablename__ = 'jobs'

    id: Mapped[int] = mapped_column(primary_key=True)
    font_id: Mapped[Optional[int]] = mapped_column(ForeignKey('fonts.id', ondelete='SET NULL'), nullable=True, index=True)

    # Processing state
    # Staus can either be: pending, processing, completed, failed
    status: Mapped[str] = mapped_column(String(20), default='pending', index=True)
    progress: Mapped[int] = mapped_column(Integer, default=0)  # 0-100
    current_metric: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Metrics (stored as JSON arrays of metric names)
    requested_metrics: Mapped[list] = mapped_column(JSON, default=list)
    completed_metrics: Mapped[list] = mapped_column(JSON, default=list)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Relationships
    font: Mapped[Optional['Font']] = relationship('Font', back_populates='jobs')
    computed_metrics: Mapped[list['FontMetric']] = relationship('FontMetric', back_populates='job')

    def serialize(self) -> dict:
        return {
            'job_id': self.id,
            'font_id': self.font_id,
            'font_name': self.font.name if self.font else None,
            'typeface_name': self.font.typeface.name if self.font and self.font.typeface else None,
            'status': self.status,
            'progress': self.progress,
            'current_metric': self.current_metric,
            'error': self.error,
            'requested_metrics': self.requested_metrics,
            'completed_metrics': self.completed_metrics,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
        }
