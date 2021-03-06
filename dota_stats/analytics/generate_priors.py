# -*- coding: utf-8 -*-
"""Calculate a positional probabalitiy distribution from lane presence
on Dotabuff website and combine with `position` estimated from average gold
over LIMIT matches, and a pre-supplied position mask (e.g. force anti-mage to
position #1).

This is used to assign heroes to roles for analytics, using actual gold farmed
and a prior probability based on analysis of matches.
"""

import os
import sys
import time
import json
from datetime import datetime
import random
import requests
from bs4 import BeautifulSoup
import pandas as pd
import mariadb
import numpy as np
sys.path.append("..")
import meta             # pylint: disable=import-error, wrong-import-position

DEBUG = True
LIMIT = 100000
BASE_URL="https://www.dotabuff.com"

#------------------------------------------------------------------------------
# Step #1: Prior based on gold spent in recent matches
#------------------------------------------------------------------------------
def sort_heroes_gold(heroes_json, gold_json):
    """Sort heroes by gold spent. Inputs are hero list in JSON, a gold/hero
    dictionary. Returns a list of heroes. Nominal probability set to 1%.
    """

    heroes = json.loads(heroes_json)
    gold_dict = json.loads(gold_json)

    gold = []
    for this_hero in heroes:
        gold.append(gold_dict[str(this_hero)])

    return [b for _, b in sorted(zip(gold,heroes), reverse=True)]

def prior_from_matches(limit):
    """Based on <limit> matches return a farm position probability based on
    gold spent.
    """

    # Database fetch
    conn = mariaBase.connect(
        user=os.environ['DOTA_USERNAME'],
        password=os.environ['DOTA_PASSWORD'],
        host=os.environ['DOTA_HOSTNAME'],
        database=os.environ['DOTA_DATABASE'])
    cursor=conn.cursor()

    stmt= "SELECT match_id, radiant_heroes, dire_heroes, gold_spent FROM "
    stmt+="dota_matches LIMIT {}".format(limit)
    cursor.execute(stmt)
    rows=cursor.fetchall()

    # Process each row
    position_array = np.zeros([meta.NUM_HEROES, 5])
    positions = range(5)
    for row in rows:
        radiant = sort_heroes_gold(row[1], row[3])
        for rhero, pos in zip(radiant, positions):
            i_hero = meta.HEROES.index(rhero)
            position_array[i_hero, pos]+=1

        dire = sort_heroes_gold(row[2], row[3])
        for dhero, pos in zip(dire, positions):
            i_hero = meta.HEROES.index(dhero)
            position_array[i_hero, pos] += 1

    # Create dataframe and normalize...
    df_prior_spent = pd.DataFrame(position_array)
    df_prior_spent = df_prior_spent.div(df_prior_spent.sum(axis=1), axis=0)
    df_prior_spent.columns = ["P1", "P2", "P3", "P4", "P5"]
    df_prior_spent.index = meta.HERO_DICT.values()

    df_prior_spent[df_prior_spent<0.01]=0.01
    df_prior_spent = df_prior_spent.div(df_prior_spent.sum(axis=1), axis=0)

    # Re-sort rows according to meta
    hlist = list(meta.HERO_DICT.values())
    df_prior_spent = df_prior_spent.reindex(hlist)

    return df_prior_spent

#------------------------------------------------------------------------------
# Step #2: Lane presence from Dotabuff
#------------------------------------------------------------------------------
def prior_from_lanes():
    """Develop priors based on lane presences. Dotabuff does not assign a role
    (e.g. carry) for every match, but it does report which lane the hero was
    in by %. Nominal probability set to 1% to allow other outcomes."""

    headers = {
            'User-Agent' : 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                        'AppleWebKit/537.36 (KHTML, like Gecko)'
                        ' Chrome/74.0.3729.169 Safari/537.36'
            }

    rv1 = requests.get("{}/heroes".format(BASE_URL), headers=headers)

    if rv1.status_code != 200:
        raise ValueError("Non-200 return code from main page")

    soup = BeautifulSoup(rv1.text, 'html.parser')
    hero_grid =soup.find("div", {'class' : 'hero-grid'})

    tuples=[]
    for link in [t.get("href") for t in hero_grid.find_all("a")]:

        hero=link.split("/")[2] #.replace("-", "_").replace("'","")
        print(hero)

        rv2 = requests.get("{}/{}".format(BASE_URL, link),
                            headers=headers)

        if rv2.status_code != 200:
            raise ValueError("Non-200 return code from hero page")


        bs2=BeautifulSoup(rv2.text, 'html.parser')
        lane_pres=[t for t in bs2.find_all("section") if \
                    t.header.text=='Lane Presence'][0]

        for table_row in lane_pres.tbody.find_all("tr"):
            table_entry=table_row.find_all("td")

            # Append hero, lane, presence
            tuples.append((
                hero,
                table_entry[0].text,
                float(table_entry[1].text.replace("%",""))/100.0))

        time.sleep(random.uniform(0,0.25))

    # Create data frame, eliminate non safe/off/mid lane, and renormalize
    df_lane = pd.DataFrame(tuples)
    df_lane.columns=['hero','lane','presence']
    df_lane = df_lane.pivot(index='hero', columns='lane', values='presence')
    df_lane = df_lane.fillna(0)
    df_lane = df_lane[['Mid Lane','Safe Lane', 'Off Lane']]
    df_lane = df_lane.div(df_lane.sum(axis=1),axis=0)

    # Rename the columns, duplicate P2/P5 probability from P1/P3
    # probability
    df_lane = df_lane.rename(columns={'Safe Lane' : 'P1',
                                      'Mid Lane' : 'P2',
                                      'Off Lane' : 'P3'})
    df_lane['P5']=df_lane['P1']
    df_lane['P4']=df_lane['P3']
    df_lane=df_lane[["P{}".format(t+1) for t in range(5)]]

    # Make sure probability is at least ~0.01
    df_lane[df_lane<0.01]=0.01
    df_lane = df_lane.div(df_lane.sum(axis=1),axis=0)

    # Re-sort rows according to meta
    hlist = list(meta.HERO_DICT.values())
    df_lane = df_lane.reindex(hlist)

    return df_lane

#------------------------------------------------------------------------------
# Step #3 positional masking
#------------------------------------------------------------------------------
def prior_from_mask():
    """Prior from manual mask, this was hand edited."""

    # Read from disk
    df_mask = pd.read_csv("prior_mask.csv", index_col=0)

    # Make sure probability is at least ~0.01
    df_mask[df_mask<0.01]=0.01
    df_mask = df_mask.div(df_mask.sum(axis=1),axis=0)

    # Re-sort rows according to meta
    hlist = list(meta.HERO_DICT.values())
    df_mask = df_mask.reindex(hlist)

    return df_mask


#------------------------------------------------------------------------------
# Main Entry Point
#------------------------------------------------------------------------------
def main():
    """Main entry point"""

    df_prior_spent = prior_from_matches(LIMIT)
    df_prior_lane = prior_from_lanes()
    df_prior_mask = prior_from_mask()

    # Multiply and renormalize
    df_prior = df_prior_spent.multiply(df_prior_lane).multiply(df_prior_mask)
    df_prior[df_prior<0.001] = 0.001
    df_prior = df_prior.div(df_prior.sum(axis=1),axis=0)

    # Export to JSON
    export = {}
    export['prior'] = df_prior.to_dict()
    export['version'] = datetime.utcnow().isoformat()

    with open("prior_final.json", "w") as filename:
        filename.write(json.dumps(export, indent=4))

    # Export to CSV
    df_prior.to_csv("prior_final.csv")

    if DEBUG:
        df_prior_spent.to_csv("__prior_spent.csv")
        df_prior_lane.to_csv("__prior_lane.csv")
        df_prior_mask.to_csv("__prior_mask.csv")


if __name__ == "__main__":
    main()
