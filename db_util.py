# -*- coding: utf-8 -*-
"""Utility functions to manage the MySQL database, includes SQLAlchemy
classes and functionality.
"""
from sqlalchemy import Column, CHAR, VARCHAR, BigInteger, Integer, Float
from sqlalchemy.dialects.mysql import TINYINT
from sqlalchemy.ext.declarative import declarative_base
from server.server import db

Base = declarative_base()
# pylint: disable=too-few-public-methods, no-member


class Configuration(Base):
    """Contains database configuration data include version number"""
    __tablename__ = 'configuration'
    config_id = Column(CHAR(64), primary_key=True)
    value = Column(VARCHAR(256))

    def __repr__(self):
        return '<%s>' % self.config_id


class Match(Base):
    """Base class for match results"""
    __tablename__ = 'dota_matches'

    match_id = Column(BigInteger, primary_key=True)
    start_time = Column(BigInteger)
    radiant_heroes = Column(CHAR(32))
    dire_heroes = Column(CHAR(32))
    radiant_win = Column(TINYINT)
    api_skill = Column(Integer)
    items = Column(VARCHAR(1024))
    gold_spent = Column(VARCHAR(1024))

    def __repr__(self):
        return '<Match %r Radiant %r Dire %r>' % (
            self.match_id, self.radiant_heroes, self.dire_heroes)


class FetchHistory(Base):
    """Which matches have already been fetched"""
    __tablename__ = 'fetch_history'

    match_id = Column(BigInteger, primary_key=True)
    start_time = Column(BigInteger)


class FetchSummary(Base):
    """Base class for fetch summary stats"""
    __tablename__ = 'fetch_summary'
    date_hour_skill = Column(CHAR(32), primary_key=True)
    skill = Column(Integer)
    rec_count = Column(Integer)


class WinRatePickRate(Base):
    """Base class for fetch_win_rate object."""

    __tablename__ = "fetch_win_rate"
    hero_skill = Column(CHAR(128), primary_key=True)
    skill = Column(TINYINT)
    hero = Column(CHAR(128))
    time_range = Column(CHAR(128))
    radiant_win = Column(Integer)
    radiant_total = Column(Integer)
    radiant_win_pct = Column(Float)
    dire_win = Column(Integer)
    dire_total = Column(Integer)
    dire_win_pct = Column(Float)
    win = Column(Integer)
    total = Column(Integer)
    win_pct = Column(Float)


class WinByPosition(Base):
    """Win rates by position for all heroes"""
    __tablename__ = 'win_by_position'

    timestamp_hero_skill = Column(VARCHAR(128), primary_key=True,
                                  nullable=False)
    hero = Column(VARCHAR(64), nullable=False)
    pos1 = Column(Float, nullable=True)
    pos2 = Column(Float, nullable=True)
    pos3 = Column(Float, nullable=True)
    pos4 = Column(Float, nullable=True)
    pos5 = Column(Float, nullable=True)


def get_version():
    """Return current database version"""
    if not db.engine.dialect.has_table(db.engine, "configuration"):
        return "001"

    version = db.session.query(Configuration).filter_by(
        config_id='VERSION').first().value
    return version


def create_version_001():
    """Create the initial database version"""

    if db.engine.dialect.has_table(db.engine, "dota_matches"):
        Match.__table__.drop(db.engine)
    Match.__table__.create(db.engine)


def update_version_002():
    """Add bitmask fields and table for winrate by position"""

    if get_version() != "001":
        return

    Configuration.__table__.create(db.engine)
    config = Configuration()
    config.config_id = "VERSION"
    config.value = "002"

    db.session.add(config)
    db.session.commit()

    # Create win position table
    if db.engine.dialect.has_table(db.engine, "win_by_position"):
        WinByPosition.__table__.drop(db.engine)
    WinByPosition.__table__.create(db.engine)

    return


def main():
    """Main entry point"""
    update_version_002()


if __name__ == "__main__":
    main()
