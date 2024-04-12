import sys
import os

sys.path.append(
    os.path.abspath("../bot-example")
)
from time import sleep
from pprint import pprint
from collections import OrderedDict
from typing import *
from time import time
from datetime import datetime
from collections import defaultdict
import concurrent.futures

import algotrade_api
from algotrade_api import AlgotradeApi, PowerPlant, Resource

from logging import getLogger, basicConfig, INFO, DEBUG, FileHandler

pool = concurrent.futures.ThreadPoolExecutor(max_workers=8)

basicConfig(
    filename=f"logs/{time()}.log",
    filemode="a",
    format="%(asctime)s,%(msecs)d %(name)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
    level=DEBUG,
)

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

MONEY = 0

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

TOTAL_PRICE_SOLD_ENERGY = 0

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
    ]
    r_plants, r_dataset, r_orders, r_player, r_matched_trades = [
        f.result() for f in futures_list
    ]
    if any([r.status_code != 200 for r in [r_plants, r_dataset, r_orders, r_player]]):
        logger.debug("Error in fetching data, retrying")
        sleep(TICK_TIME)
        on_tick_start(api)
    else:
        global PLANTS_PRICES, OWNED_PLANTS, POWERED_PLANTS, PLANT_SELL_PRICES, DATASET, ORDERS, MONEY, MATCHED_TRADES, CURRENT_VOLUME, ENERGY_PRICE_PER_HOUR, CURRENT_VOLUME, CURRENT_HOUR, OUTPUT_PLANTS, ROI
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

        logger.debug(f"Money: {MONEY}")
        logger.debug(f"Matched trades: {MATCHED_TRADES}")

        global TOTAL_PRICE_SOLD_ENERGY
        TOTAL_PRICE_SOLD_ENERGY = get_total_price_sold_energy()

        logger.debug(f"Total price sold energy: {TOTAL_PRICE_SOLD_ENERGY}")


def get_energy_price(mean_energy_price_per_hour) -> float:
    return DATASET["max_energy_price"] * ENERGY_DISCOUNT
    # return (
    #     min(
    #         DATASET["max_energy_price"],
    #         mean_energy_price_per_hour[int((CURRENT_HOUR + 1) % 24)],
    #     )
    #     * ENERGY_DISCOUNT
    # )

def sum_of_matched_trades(matched_trades):
    result = 0.0
    buy = matched_trades.get("buy", [])
    for order in buy:
        result -= order['total_price']

    sell = matched_trades.get("sell", [])
    for order in sell:
        result += order['total_price']

    logger.debug(f"Sum of matched trades: {result}")
    return result

def get_total_price_sold_energy():
    s = sum_of_matched_trades(MATCHED_TRADES)
    return MONEY - s
    



def check_if_power_plant_running(api: AlgotradeApi, resource: Resource):
    global MONEY

    if OWNED_PLANTS[resource.value] == 0:
        if MONEY < PLANTS_PRICES[resource.value]:
            logger.debug(f"Not enough money to buy {resource.value} plant")
            return False
        else:
            try:
                r = api.buy_plant(resource.value)
                MONEY -= PLANTS_PRICES[resource.value]
            except Exception as e:
                logger.debug(f"Error buying plant: {e}")
                return False
            logger.debug(f"Buying {resource.value} plant, response: {r.text}")
    if POWERED_PLANTS[resource.value] < OWNED_PLANTS[resource.value]:
        try:
            r = api.turn_on(resource.value, OWNED_PLANTS[resource.value])
            logger.debug(f"Turning on {resource.value} plant, response: {r.text}")
            POWERED_PLANTS[resource.value] = OWNED_PLANTS[resource.value]
        except Exception as e:
            logger.debug(f"Error turning on plant: {e}")
            return False
    else:
        N_NEXT_BUY_PLANTS_TRIES[resource.value] += 1
        if N_NEXT_BUY_PLANTS_TRIES[resource.value] >= BUY_AFTER_N_SUCCESSFUL_TRIES:
            N_NEXT_BUY_PLANTS_TRIES[resource.value] = 0
            try:
                r = api.buy_plant(resource.value)
                r = api.turn_on(resource.value, OWNED_PLANTS[resource.value])
                POWERED_PLANTS[resource.value] = OWNED_PLANTS[resource.value]
            except Exception as e:
                logger.debug(f"Error buying plant: {e}")
                return False

    return True


def asset_arbitrage(
    api: AlgotradeApi,
    resource: Resource,
    energy_price: float,
):
    if resource.value not in ORDERS:
        logger.debug(f"No orders for {resource.value}")
        return
    if "sell" not in ORDERS[resource.value]:
        logger.debug(f"No sell orders for {resource.value}")
        return
    resource_price = ORDERS[resource.value]["sell"]
    resource_price = sorted(resource_price, key=lambda x: x["price"])

    logger.debug(f"Energy price: {energy_price}")
    success_at_least_one = False
    for i in range(len(resource_price)):

        if (
            resource_price[i]["price"]
            * (1 + BUY_MARGIN)
            / DATASET["power_plants_output"][resource.value]
            < energy_price
        ):
            if not check_if_power_plant_running(api, resource):
                continue

            if CURRENT_VOLUME[resource.value] > MAX_VOLUME[resource.value]:
                logger.debug(f"Volume of {resource.value} is too high")
                break

            actual_size = min(
                resource_price[i]["size"],
                OWNED_PLANTS[resource.value] * 2 - CURRENT_VOLUME[resource.value],
            )
            r = api.create_order(
                resource=resource.value,
                price=resource_price[i]["price"] * (1 + BUY_MARGIN),
                size=actual_size,
                side="buy",
                expiration_length=4,
            )

            global MONEY
            MONEY -= (
                resource_price[i]["price"]
                * (1 + BUY_MARGIN)
                * resource_price[i]["size"]
            )

            logger.debug(
                f"Buying {resource.value} price: {resource_price[i]['price'] * (1 + BUY_MARGIN)}, size: {actual_size}, response: {r.text}"
            )

            success_at_least_one = True

        if not success_at_least_one:
            N_NEXT_BUY_PLANTS_TRIES[resource.value] = 0

        break


def roi(output_list_plants, plants_price):
    mean_output = sum(output_list_plants) / len(output_list_plants)
    roi = mean_output / plants_price
    return roi


def roi2unconvertible_plants(energy_price: float) -> List[Resource]:
    output = dict()
    for resource in Resource:
        if resource.value in UNRENOVABLE:
            output[resource] = (
                ROI[resource.value] * energy_price
                - DATASET["resource_prices"][resource.value]
                / PLANTS_BUY_PRICES[resource.value]
            )

    output = sorted(output.items(), key=lambda x: x[1], reverse=True)
    output = [x[0] for x in output]
    return output


def on_tick_end(api: AlgotradeApi):
    pass


def tick():
    # Get current player stats
    start = time()
    on_tick_start(api)

    mean_energy_price_per_hour = {
        hour: sum(prices) / len(prices)
        for hour, prices in ENERGY_PRICE_PER_HOUR.items()
    }

    for i in range(24):
        if i not in mean_energy_price_per_hour:
            mean_energy_price_per_hour[i] = DATASET["max_energy_price"]

    energy_price = get_energy_price(mean_energy_price_per_hour)  # max energy price
    api.set_energy_price(energy_price)

    order = roi2unconvertible_plants(energy_price)
    for resource in order:
        if resource.value in UNRENOVABLE:
            asset_arbitrage(api, resource, energy_price)

    end = time()

    logger.debug(f"Tick took {end - start} seconds")


if __name__ == "__main__":
    run_with_inputs()
