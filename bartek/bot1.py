import sys
import os

os.chdir(os.path.dirname(__file__))

sys.path.append(os.path.join(os.path.dirname(__file__), "../bot-example"))
from time import sleep
from pprint import pprint
from collections import OrderedDict
from typing import *
from time import time
from datetime import datetime
from collections import defaultdict
import concurrent.futures
import numpy as np
import random

import algotrade_api
from algotrade_api import AlgotradeApi, PowerPlant, Resource

from logging import getLogger, basicConfig, INFO, DEBUG, FileHandler, CRITICAL

pool = concurrent.futures.ThreadPoolExecutor(max_workers=8)

basicConfig(
    filename=f"logs/{time()}.log",
    filemode="a",
    format="%(asctime)s,%(msecs)d %(name)s %(levelname)s %(message)s %(lineno)d",
    datefmt="%H:%M:%S",
    level=DEBUG,
)

urlib_logger = getLogger("urllib3.connectionpool")
urlib_logger.setLevel(CRITICAL)
logger = getLogger(__name__)
logger.setLevel(DEBUG)

# Change this at the start of the competition
url = "https://algotrade-server.xfer.hr"  # Change this
team_secret = "9EJ6MAV3N5"  # Change this


api = AlgotradeApi(url, team_secret)

TICK_TIME = 0.01

ENERGY_DISCOUNT = 0.8
ENERGY_DECAY = 0.95
BUY_MARGIN = 0.10

UNRENOVABLE = [
    "coal",
    "oil",
    "gas",
    "biomass",
    "uranium",
]
RENOVABLE = ["geothermal", "wind", "solar", "hydro"]

MONEY_START = 50000000
MINIMUM_MONEY_LEVEL_PER_PLANT = 0
MONEY = MONEY_START
MONEY_HISTORY = []  # TODO: change base, keeps previous history, without current
PLANTS_SPENT_LAST_STEP = 0

PLANTS_BUY_PRICES: Dict[str, int]
OWNED_PLANTS: Dict[str, int]
POWERED_PLANTS: Dict[str, int]
PLANT_SELL_PRICES: Dict[str, int]
# {
#     "coal": 0,
#     "uranium": 0,
#     "biomass": 0,
#     "gas": 1,
#     "oil": 0,
#     "geothermal": 0,
#     "wind": 0,
#     "solar": 0,
#     "hydro": 0,
# }
# ---------------------
DATASET = Dict[str, Any]
# {
#     "tick": 312,
#     "date": "2011-11-21T05:30:00",
#     "resource_prices": {
#         "coal": 20326,
#         "uranium": 93015,
#         "biomass": 68678,
#         "gas": 54367,
#         "oil": 57818,
#     },
#     "power_plants_output": {
#         "coal": 113,
#         "uranium": 1491,
#         "biomass": 130,
#         "gas": 304,
#         "oil": 384,
#         "geothermal": 63,
#         "wind": 8,
#         "solar": 0,
#         "hydro": 124,
#     },
#     "energy_demand": 23274,
#     "max_energy_price": 610,
# }
# ---------------------
ORDERS = Dict[str, Any]
# {'gas': {'buy': [{'order_id': '01HV9VQYD8QP78XJ2Z2YFJSF15',
#     'player_id': '01HV9VADH3T3C115TT6F81M6Q3',
#     'price': 54449,
#     'size': 12,
#     'tick': 312,
#     'timestamp': '2024-04-12T19:14:55.528247',
#     'order_side': 'buy',
#     'order_status': 'active',
#     'filled_size': 0,
#     'expiration_tick': 316}],
#   'sell': [{'order_id': '01HV9VQYD8P24YAFMP3D3JXCC8',
#     'player_id': '01HV9VADH3T3C115TT6F81M6Q3',
#     'price': 54450,
#     'size': 100,
#     'tick': 312,
#     'timestamp': '2024-04-12T19:14:55.528506',
#     'order_side': 'sell',
#     'order_status': 'active',
#     'filled_size': 0,
#     'expiration_tick': 316}]},

MAX_VOLUME = {
    "coal": 4,
    "uranium": 4,
    "biomass": 4,
    "gas": 4,
    "oil": 4,
    "geothermal": 4,
    "wind": 4,
    "solar": 4,
    "hydro": 4,
}

OUTPUT_PLANTS = {
    "coal": [],
    "uranium": [],
    "biomass": [],
    "gas": [],
    "oil": [],
    "geothermal": [],
    "wind": [],
    "solar": [],
    "hydro": [],
}

ROI = {}

CURRENT_VOLUME = {}
CURRENT_HOUR = 0

ENERGY_PRICE_PER_HOUR = defaultdict(list)
MEAN_ENERGY_PRICE_PER_HOUR = {}

N_NEXT_BUY_PLANTS_TRIES = defaultdict(int)
BUY_AFTER_N_SUCCESSFUL_TRIES = 10
RENOVABLE_BUY_AFTER_N_SUCCESSFUL_TRIES = 15

CURRENT_TICK = 0

ENERGY_ORDERS = {}
ENERGY_DEMAND = 0

N_MAX_ENERGY_CHECKS = 1
N_ENERGY_FAILS = 0
N_ENERGY_SUCCESSES = 0
# QUANTILE_RANGES = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.99]
QUANTILE_RANGES = [0.1, 0.15, 0.25, 0.3, 0.4, 0.45, 0.5, 0.6, 0.7, 0.8]
QUANTILES = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
CURRENT_QUANTILE = 9
PRODUCED_ENERGY = 0
SOLD_ENERGY = 0
PREV_VOLUMES = {}
PREV_POWERED_PLANTS = {}


def run_with_inputs():
    # Get all games avaliable
    games = api.get_games().json()
    pprint(games)
    i = int(input("Enter index of the game you want to play > "))
    game = games[i]

    api.set_game_id(game["game_id"])

    # Get players you created in this game
    players = api.get_players().json()
    pprint(players)
    i = int(
        input("Enter index of the player you want to play with, -1 to create new > ")
    )

    if i == -1:
        player_name = input("Name of your player >")
        response = api.create_player(player_name)
        pprint(response.json())
        player_id = response.json()["player_id"]
    else:
        player_id = players[i]["player_id"]
    api.set_player_id(player_id)

    input("Start loop (press enter to continue) >")
    run_with_params()


def run_with_params(game_id: str = None, player_id: str = None):
    # If you want to run the game directly from main, set these parameters
    if game_id is not None:
        api.set_game_id(game_id)
    if player_id is not None:
        api.set_player_id(player_id)

    on_game_init(api)

    while True:
        tick()
        sleep(TICK_TIME)


def on_game_init(api: AlgotradeApi):

    r = api.get_plants()
    if r.status_code != 200:
        sleep(TICK_TIME)
        on_game_init(api)
    else:
        global PLANTS_BUY_PRICES, OWNED_PLANTS, POWERED_PLANTS, PLANT_SELL_PRICES
        r = r.json()
        PLANTS_BUY_PRICES = r["buy_price"]
        OWNED_PLANTS = r["power_plants_owned"]
        POWERED_PLANTS = r["power_plants_powered"]
        PLANT_SELL_PRICES = r["sell_price"]


def on_tick_start(api: AlgotradeApi):
    # r_plants = api.get_plants()
    # r_dataset = api.get_dataset()
    # r_orders = api.get_orders(restriction="best")
    # r_player = api.get_player()
    # r_matched_trades = api.get_matched_trades()
    futures_list = [
        pool.submit(api.get_plants),
        pool.submit(api.get_dataset),
        pool.submit(api.get_orders, restriction="best"),
        pool.submit(api.get_player),
        pool.submit(api.get_matched_trades),
        pool.submit(api.eneregy_demand),
    ]
    r_plants, r_dataset, r_orders, r_player, r_matched_trades, r_energy_demand = [
        f.result() for f in futures_list
    ]
    if any(
        [
            r.status_code != 200
            for r in [r_plants, r_dataset, r_orders, r_player, r_energy_demand]
        ]
    ):
        logger.debug("Error in fetching data, retrying")
        sleep(TICK_TIME)
        on_tick_start(api)
    else:
        global PLANTS_PRICES, OWNED_PLANTS, POWERED_PLANTS, PLANT_SELL_PRICES, DATASET, ORDERS, MONEY, MATCHED_TRADES, CURRENT_VOLUME, ENERGY_PRICE_PER_HOUR, CURRENT_VOLUME, CURRENT_HOUR, OUTPUT_PLANTS, ROI, ENERGY_DEMAND, MINIMUM_MONEY_LEVEL_PER_PLANT, ENERGY_ORDERS, CURRENT_TICK, SOLD_ENERGY, PRODUCED_ENERGY
        r_plants = r_plants.json()
        PLANTS_PRICES = r_plants["buy_price"]
        OWNED_PLANTS = r_plants["power_plants_owned"]
        POWERED_PLANTS = r_plants["power_plants_powered"]
        PLANT_SELL_PRICES = r_plants["sell_price"]

        DATASET = [v for v in r_dataset.json().values()][0]
        for key, value in DATASET["power_plants_output"].items():
            OUTPUT_PLANTS[key].append(value)
            if len(OUTPUT_PLANTS[key]) > 14 * 24:
                OUTPUT_PLANTS[key] = OUTPUT_PLANTS[key][: 14 * 24]
        CURRENT_TICK = DATASET["tick"]
        PREV_VOLUMES[CURRENT_TICK] = CURRENT_VOLUME
        PREV_POWERED_PLANTS[CURRENT_TICK] = POWERED_PLANTS
        if CURRENT_TICK - 2 in PREV_VOLUMES:
            PREV_VOLUMES.pop(CURRENT_TICK - 2)
        if CURRENT_TICK - 2 in PREV_POWERED_PLANTS:
            PREV_POWERED_PLANTS.pop(CURRENT_TICK - 2)

        ROI = {
            key: roi(value, PLANTS_PRICES[key]) for key, value in OUTPUT_PLANTS.items()
        }

        hour = datetime.fromisoformat(DATASET["date"]).hour
        CURRENT_HOUR = hour
        ENERGY_PRICE_PER_HOUR[hour].append(DATASET["max_energy_price"])
        ENERGY_PRICE_PER_HOUR[hour] = ENERGY_PRICE_PER_HOUR[hour][-5:]

        ORDERS = r_orders.json()

        MONEY = r_player.json()["money"]
        CURRENT_VOLUME = r_player.json()["resources"]

        MATCHED_TRADES = r_matched_trades.json()

        MINIMUM_MONEY_LEVEL_PER_PLANT = 0
        for k, v in OWNED_PLANTS.items():
            if k in UNRENOVABLE:
                MINIMUM_MONEY_LEVEL_PER_PLANT += v * DATASET["resource_prices"][k] * 2

        ENERGY_ORDERS = [v for v in r_energy_demand.json().values()][0]
        ENERGY_ORDERS = sorted(ENERGY_ORDERS, key=lambda x: x["trade_price"])
        ENERGY_DEMAND = DATASET["energy_demand"]

        PRODUCED_ENERGY = 0
        if CURRENT_TICK - 1 in PREV_VOLUMES and CURRENT_TICK - 1 in PREV_POWERED_PLANTS:
            for key, value in PREV_VOLUMES[CURRENT_TICK - 1].items():
                PRODUCED_ENERGY += (
                    min(value, PREV_POWERED_PLANTS[CURRENT_TICK - 1][key])
                    * DATASET["power_plants_output"][key]
                )
            for key, value in PREV_POWERED_PLANTS[CURRENT_TICK - 1].items():
                if key in RENOVABLE:
                    PRODUCED_ENERGY += value * DATASET["power_plants_output"][key]
        my_energy_orders = [
            x for x in ENERGY_ORDERS if x["sell_player_id"] == api.player_id
        ]
        SOLD_ENERGY = sum([x["trade_size"] for x in my_energy_orders])

        if len(ENERGY_ORDERS) > 0:
            prices, volumes = process_past_orders()
            for index, q_range in zip(range(len(QUANTILE_RANGES)), QUANTILE_RANGES):
                QUANTILES[index] = prices[
                    min(
                        np.searchsorted(volumes, np.quantile(volumes, q_range)),
                        len(volumes) - 1,
                    )
                ]

        logger.debug(
            f"""\
PLANTS_PRICES {PLANTS_PRICES}\n
OWNED_PLANTS {OWNED_PLANTS}\n
POWERED_PLANTS {POWERED_PLANTS}\n
PLANT_SELL_PRICES {PLANT_SELL_PRICES}\n
DATASET {DATASET}\n
CURRENT_HOUR {CURRENT_HOUR}\n
Matched trades: {len(MATCHED_TRADES['buy'])}
MINIMUM_MONEY_LEVEL_PER_PLANT: {MINIMUM_MONEY_LEVEL_PER_PLANT}
ENERGY_DEMAND: {ENERGY_DEMAND} 
SOLD_ENERGY: {SOLD_ENERGY}
QUANTILES: {QUANTILES}
N_ENERGY_FAILS: {N_ENERGY_FAILS}
N_ENERGY_SUCCESSES: {N_ENERGY_SUCCESSES}
CURRENT_QUANTILE: {CURRENT_QUANTILE}
CURRENT_QUANTILE_PRICE: {QUANTILES[CURRENT_QUANTILE]}
PRODUCED_ENERGY: {PRODUCED_ENERGY}
SOLD_ENERGY: {SOLD_ENERGY}
POWER PLANTS OUTPUT: {DATASET['power_plants_output']}
MONEY {MONEY}
"""
        )

        logger.debug(list(zip(prices, volumes)))


def process_past_orders():
    prices = []
    volumes = []
    counter = 0

    for order in ENERGY_ORDERS:
        counter += order["trade_size"]
        prices.append(order["trade_price"])
        volumes.append(counter)
        if counter >= ENERGY_DEMAND:
            break

    return prices, volumes


def get_energy_price() -> float:
    global CURRENT_VOLUME, ENERGY_PRICE_PER_HOUR, CURRENT_HOUR, ENERGY_DISCOUNT, ENERGY_DECAY, ENERGY_DEMAND, PRODUCED_ENERGY, SOLD_ENERGY, N_ENERGY_FAILS, N_ENERGY_SUCCESSES, CURRENT_QUANTILE, QUANTILES, N_MAX_ENERGY_CHECKS
    logger.debug(f"SOLD_ENERGY: {SOLD_ENERGY}, PRODUCED_ENERGY: {PRODUCED_ENERGY}")
    if SOLD_ENERGY * 2 < PRODUCED_ENERGY:
        N_ENERGY_FAILS += 1
        N_ENERGY_SUCCESSES = 0
    else:
        N_ENERGY_FAILS = 0
        N_ENERGY_SUCCESSES += 1

    if N_ENERGY_FAILS >= N_MAX_ENERGY_CHECKS:
        CURRENT_QUANTILE -= 1
        CURRENT_QUANTILE = max(CURRENT_QUANTILE, 0)
        N_ENERGY_FAILS = 0
        N_ENERGY_SUCCESSES = 0

    if N_ENERGY_SUCCESSES >= N_MAX_ENERGY_CHECKS:
        CURRENT_QUANTILE += 1
        CURRENT_QUANTILE = min(CURRENT_QUANTILE, 8)
        N_ENERGY_FAILS = 0
        N_ENERGY_SUCCESSES = 0

    return QUANTILES[CURRENT_QUANTILE]


def check_if_power_plant_running(api: AlgotradeApi, resource: Resource):
    global MONEY

    if OWNED_PLANTS[resource.value] == 0:
        if MONEY - MINIMUM_MONEY_LEVEL_PER_PLANT < PLANTS_PRICES[resource.value]:
            logger.debug(f"Not enough money to buy {resource.value} plant")
            return False
        else:
            try:
                r = api.buy_plant(resource.value)
                if r.status_code != 200:
                    logger.debug(f"Error buying plant: {r.text}")
                    return False
                MONEY -= PLANTS_PRICES[resource.value]
                N_NEXT_BUY_PLANTS_TRIES[resource.value] = 0
                OWNED_PLANTS[resource.value] += 1
            except Exception as e:
                logger.debug(f"Error buying plant: {e}")
                return False
            logger.debug(f"Buying {resource.value} plant, response: {r.text}")
    if POWERED_PLANTS[resource.value] < OWNED_PLANTS[resource.value]:
        try:
            r = api.turn_on(resource.value, OWNED_PLANTS[resource.value])
            logger.debug(f"Turning on {resource.value} plant, response: {r.text}")
            POWERED_PLANTS[resource.value] = OWNED_PLANTS[resource.value]
            return True
        except Exception as e:
            logger.debug(f"Error turning on plant: {e}")
            return False
    else:
        N_NEXT_BUY_PLANTS_TRIES[resource.value] += 1
        if N_NEXT_BUY_PLANTS_TRIES[resource.value] >= BUY_AFTER_N_SUCCESSFUL_TRIES:
            N_NEXT_BUY_PLANTS_TRIES[resource.value] = 0
            try:
                r = api.buy_plant(resource.value)
                OWNED_PLANTS[resource.value] += 1
                r = api.turn_on(resource.value, OWNED_PLANTS[resource.value])
                POWERED_PLANTS[resource.value] = OWNED_PLANTS[resource.value]
            except Exception as e:
                logger.debug(f"Error buying plant: {e}")
                return False

    return True


def asset_arbitrage(
    api: AlgotradeApi,
    resource: PowerPlant,
    energy_price: float,
):
    global MONEY, CURRENT_VOLUME, ORDERS, N_NEXT_BUY_PLANTS_TRIES

    if resource.value not in ORDERS and resource.value not in RENOVABLE:
        logger.debug(f"No orders for {resource.value}")
        return
    if resource.value not in RENOVABLE and "sell" not in ORDERS[resource.value]:
        logger.debug(f"No sell orders for {resource.value}")
        return

    if resource.value in RENOVABLE:
        resource_price = [{"price": 0, "size": 0}]
    else:
        resource_price = ORDERS[resource.value]["sell"]
        resource_price = sorted(resource_price, key=lambda x: x["price"])

    logger.debug(f"Energy price: {energy_price}")
    success_at_least_one = False
    for i in range(len(resource_price)):

        if (
            resource_price[i]["price"]
            * (1 + BUY_MARGIN)
            / (DATASET["power_plants_output"][resource.value] + 1)
            < energy_price
        ):
            if not check_if_power_plant_running(api, resource):
                break
            if resource.value in RENOVABLE:
                success_at_least_one = True
                continue

            actual_size = max(
                min(
                    resource_price[i]["size"],
                    OWNED_PLANTS[resource.value] * 2 - CURRENT_VOLUME[resource.value],
                ),
                0,
            )

            if actual_size == 0:
                logger.debug(f"Volume of {resource.value} is too high")
                break

            actual_size = max(
                min(
                    actual_size,
                    MONEY // abs(resource_price[i]["price"] * (1 + BUY_MARGIN)),
                ),
                0,
            )

            if actual_size == 0:
                logger.debug(f"Not enough money to buy {resource.value}")
                break

            r = api.create_order(
                resource=resource.value,
                price=resource_price[i]["price"] * (1 + BUY_MARGIN),
                size=actual_size,
                side="buy",
                expiration_length=1,
            )

            MONEY -= (
                resource_price[i]["price"]
                * (1 + BUY_MARGIN)
                * resource_price[i]["size"]
            )
            CURRENT_VOLUME[resource.value] += actual_size

            logger.debug(
                f"Buying {resource.value} price: {resource_price[i]['price'] * (1 + BUY_MARGIN)}, size: {actual_size}, response: {r.text}"
            )

            success_at_least_one = True

        if not success_at_least_one:
            N_NEXT_BUY_PLANTS_TRIES[resource.value] = 0


def roi(output_list_plants, plants_price):
    mean_output = sum(output_list_plants) / len(output_list_plants)
    roi = mean_output / plants_price
    return roi


def roi2unconvertible_plants(energy_price: float) -> List[Resource]:
    global ROI, DATASET, PLANTS_BUY_PRICES, UNRENOVABLE, RENOVABLE

    output = dict()
    for resource in PowerPlant:
        if resource.value in UNRENOVABLE:
            output[resource] = (
                ROI[resource.value] * energy_price
                - DATASET["resource_prices"][resource.value]
                / PLANTS_BUY_PRICES[resource.value]
            )
        elif resource.value != Resource.ENERGY.value:
            output[resource] = ROI[resource.value] * energy_price

    output = sorted(output.items(), key=lambda x: x[1], reverse=True)
    logger.debug(f"ROI: {output}")
    output = [x[0] for x in output]
    return output


def on_tick_end(api: AlgotradeApi):
    pass


def tick():
    # Get current player stats
    start = time()
    on_tick_start(api)

    # mean_energy_price_per_hour = {
    #     hour: sum(prices) / len(prices)
    #     for hour, prices in ENERGY_PRICE_PER_HOUR.items()
    # }

    # for i in range(24):
    #     if i not in mean_energy_price_per_hour:
    #         mean_energy_price_per_hour[i] = DATASET["max_energy_price"]

    energy_price = get_energy_price()  # max energy price
    api.set_energy_price(int(energy_price))

    order = roi2unconvertible_plants(energy_price)
    # try_buy_renovable(order)
    for resource in order:
        if resource.value != Resource.ENERGY.value:
            asset_arbitrage(api, resource, energy_price)

    end = time()

    logger.debug(f"Tick took {end - start} seconds")


if __name__ == "__main__":
    run_with_inputs()
