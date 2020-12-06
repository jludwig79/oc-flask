# -*- coding: utf-8 -*-
"""Flask server to display analytics results"""
import json
import os
import datetime as dt
import pandas as pd
import pytz
import plotly
import plotly.graph_objs as go
from flask import Flask, render_template
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.dialects.mysql import TINYINT

app = Flask(__name__)

# Setup SQLAlchemy
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
DB_URI="mysql://{0}:{1}@{2}/{3}".format(
                os.environ['DOTA_USERNAME'],
                os.environ['DOTA_PASSWORD'],
                os.environ["DOTA_HOSTNAME"],
                os.environ['DOTA_DATABASE'],
                )
app.config['SQLALCHEMY_DATABASE_URI'] = DB_URI
db = SQLAlchemy(app)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)

# pylint: disable=no-member
#----------------------------------------------------------------------------
# SQLAlchemy Classes
#----------------------------------------------------------------------------
class Match(db.Model):
    """Base class for match results"""
    __tablename__ = 'dota_matches'

    match_id = db.Column(db.BigInteger, primary_key=True)
    start_time = db.Column(db.BigInteger)
    radiant_heroes = db.Column(db.CHAR(32))
    dire_heroes = db.Column(db.CHAR(32))
    radiant_win = db.Column(TINYINT)
    api_skill = db.Column(db.Integer)
    items = db.Column(db.VARCHAR(1024))
    gold_spent = db.Column(db.VARCHAR(1024))

    def __repr__(self):
        return '<Match %r>' % self.match_id

class FetchSummary(db.Model):
    """Base class for fetch summary stats"""
    __tablename__ = 'fetch_summary'
    date_hour_skill = db.Column(db.CHAR(32), primary_key=True)
    skill = db.Column(db.Integer)
    rec_count = db.Column(db.Integer)

class FetchWinRate(db.Model):
    """Base class for fetch_win_rate object."""

    __tablename__="fetch_win_rate"
    hero_skill = db.Column(db.CHAR(128), primary_key=True)
    skill = db.Column(TINYINT)
    hero = db.Column(db.CHAR(128))
    time_range = db.Column(db.CHAR(128))
    radiant_win = db.Column(db.Integer)
    radiant_total = db.Column(db.Integer)
    radiant_win_pct = db.Column(db.Float)
    dire_win = db.Column(db.Integer)
    dire_total = db.Column(db.Integer)
    dire_win_pct = db.Column(db.Float)
    win = db.Column(db.Integer)
    total = db.Column(db.Integer)
    win_pct = db.Column(db.Float)


class WinByPosition(db.Model):
    """Win rates by position for all heroes"""
    __tablename__ = 'win_by_position'

    timestamp_hero_skill = db.Column(db.VARCHAR(128),
                                        primary_key=True, nullable=False)
    hero = db.Column(db.VARCHAR(64), nullable=False)
    pos1 = db.Column(db.Float, nullable=True)
    pos2 = db.Column(db.Float, nullable=True)
    pos3 = db.Column(db.Float, nullable=True)
    pos4 = db.Column(db.Float, nullable=True)
    pos5 = db.Column(db.Float, nullable=True)

# pylint: enable=no-member

def get_health_metrics(days, timezone):
    """Returns a Pandas dataframe summarizing number of matches processed
    over an interval of days."""

    # Start with empty dataframe, by hour
    local_tz=pytz.timezone(timezone)

    utc_offset=local_tz.utcoffset(dt.datetime.now())
    utc_hour=int(utc_offset.total_seconds()/3600)

    now=dt.datetime.utcnow()
    now=now+utc_offset
    now_hour=dt.datetime(now.year, now.month, now.day, now.hour, 0, 0)

    times=[(now_hour-dt.timedelta(hours=i)).strftime("%Y-%m-%dT%H:00:00")\
                for i in range(24*days)]
    times=["{0}{1:+03d}00".format(t,utc_hour) for t in times]

    df_summary1=pd.DataFrame(index=times, data={
                                            1 : [0]*len(times),
                                            2 : [0]*len(times),
                                            3 : [0]*len(times),
                                          })

    # Fetch from database
    begin=int((dt.datetime.utcnow()-dt.timedelta(days=days)).timestamp())
    begin=str(begin)+"_0"
    stmt="select date_hour_skill, rec_count from fetch_summary "
    stmt+="where date_hour_skill>='{}'"
    rows=pd.read_sql_query(stmt.format(begin), db.engine)

    date_hour_skill = rows['date_hour_skill'].tolist()
    rec_count = rows['rec_count'].tolist()

    # Split out times and localize to current timezone (East Coast US)
    # Note that using pytz causes the timestamps to localize relative
    # to the stated time and not current time. To avoid discontinuities
    # we'll localize to current time.
    times=[dt.datetime.utcfromtimestamp(int(t.split("_")[0]))\
            for t in date_hour_skill]
    times=[t+utc_offset for t in times]
    times=[t.strftime("%Y-%m-%dT%H:00:00") for t in times]
    times=["{0}{1:+03d}00".format(t,utc_hour) for t in times]

    # Get remaining fields
    skills=[int(t.split("_")[1]) for t in date_hour_skill]

    # Pivot for tablular view
    df_summary2=pd.DataFrame({
        'date_hour' : times,
        'skill' : skills,
        'count' : rec_count
        })
    df_summary2=df_summary2.pivot(index='date_hour',
                                  columns='skill', values='count').\
                                          fillna(0).\
                                          astype('int32').\
                                          sort_index(ascending=False)
    df_summary=df_summary1.add(df_summary2, fill_value=0)

    # Rename columns
    df_summary=df_summary[[1,2,3]]
    df_summary.columns=['normal', 'high', 'very_high']
    df_summary=df_summary.sort_index(ascending=False)

    # For summary table
    rows=zip(df_summary.index.values,
             df_summary['normal'].values,
             df_summary['high'].values,
             df_summary['very_high'].values)

    # For plot
    fig = go.Figure(data=[
            go.Bar(name='Normal',
                   x=df_summary.index.values,
                   y=df_summary['normal']),
            go.Bar(name='High',
                   x=df_summary.index.values,
                   y=df_summary['high']),
            go.Bar(name='Very High',
                   x=df_summary.index.values,
                   y=df_summary['very_high']),
        ])
    fig.update_layout(barmode='stack')
    record_count_plot=json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)

    return record_count_plot, rows

@app.route('/')
def status():
    """Index page for server, currently contains everything on the site"""

    #---------------------------------------------------------------
    # Win rate by skill level
    #---------------------------------------------------------------

    df_sql=pd.read_sql_table("fetch_win_rate",db.engine)
    df_sql['skill']=[int(t.split("_")[-1]) for t in df_sql['hero_skill']]

    radiant_vs_dire=[]
    pick_vs_win={}

    for skill in list(set(df_sql['skill'])):
        df_sub=df_sql[df_sql['skill']==skill]
        radiant_vs_dire.append(
                100*(df_sub.sum()['radiant_win']/\
                    (df_sub.sum()['radiant_total'])))

        pick_vs_win[skill] = go.Figure(
            go.Scatter(
                x=df_sub['total'].values,
                y=df_sub['win_pct'].values,
                text=df_sub['hero'].values,
                mode='markers+text',
                textposition='top center'))

        pick_vs_win[skill].update_layout(title="Skill {0}".format(skill),
                     height=700,
                     width=700)
        pick_vs_win[skill].update_xaxes({'title' : 'Number of Games'})
        pick_vs_win[skill].update_yaxes({'title' : 'Win %'})

    win_rate_1 = json.dumps(pick_vs_win[1], cls=plotly.utils.PlotlyJSONEncoder)
    win_rate_2 = json.dumps(pick_vs_win[2], cls=plotly.utils.PlotlyJSONEncoder)
    win_rate_3 = json.dumps(pick_vs_win[3], cls=plotly.utils.PlotlyJSONEncoder)

    #---------------------------------------------------------------
    # Health metrics
    #---------------------------------------------------------------
    rec_plot14, _ = get_health_metrics(14, 'US/Eastern')
    rec_plot3, rec_count_table = get_health_metrics(3, 'US/Eastern')
    return render_template("index.html",
                            radiant_vs_dire=radiant_vs_dire,
                            win_rate_1=win_rate_1,
                            win_rate_2=win_rate_2,
                            win_rate_3=win_rate_3,
                            rec_count_table=rec_count_table,
                            rec_plot3=rec_plot3,
                            rec_plot14=rec_plot14,)
