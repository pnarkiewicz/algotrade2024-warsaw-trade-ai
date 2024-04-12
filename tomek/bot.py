import sys

sys.path.append(
    "/Users/barteksadlej/others/AlgoTrade/algotrade2024-warsaw-trade-ai/bot-example"
)
from time import sleep
from pprint import pprint
from collections import OrderedDict
from typing import *
from time import time

import algotrade_api
from algotrade_api import AlgotradeApi, PowerPlant, Resource

from logging import getLogger, basicConfig, INFO, DEBUG, FileHandler

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

TICK_TIME = 1

ENERGY_DISCOUNT = 0.8
ENERGY_DECAY = 0.95
BUY_MARGIN = 0.05

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
OUTPUT_PLANTS: Dict[str, int]
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
    "coal": 20,
    "uranium": 20,
    "biomass": 20,
    "gas": 20,
    "oil": 20,
    "geothermal": 20,
    "wind": 20,
    "solar": 20,
    "hydro": 20,
}

OUTPUT_PLANTS= {"coal": [],
        "uranium": [],
        "biomass": [],
        "gas": [],
        "oil": [],
        "geothermal": [],
        "wind": [],
        "solar": [],
        "hydro": []
        }

CURRENT_VOLUME = {}


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
        r = r.json()
        PLANTS_PRICES = r["buy_price"]
        OWNED_PLANTS = r["power_plants_owned"]
        POWERED_PLANTS = r["power_plants_powered"]
        PLANT_SELL_PRICES = r["sell_price"]


def on_tick_start(api: AlgotradeApi):
    r_plants = api.get_plants()
    r_dataset = api.get_dataset()
    r_orders = api.get_orders(restriction="best")
    r_player = api.get_player()
    r_matched_trades = api.get_matched_trades()
    if any([r.status_code != 200 for r in [r_plants, r_dataset, r_orders, r_player]]):
        logger.debug("Error in fetching data, retrying")
        sleep(TICK_TIME)
        on_tick_start(api)
    else:
        global PLANTS_PRICES, OWNED_PLANTS, POWERED_PLANTS, PLANT_SELL_PRICES, DATASET, ORDERS, MONEY, MATCHED_TRADES, CURRENT_VOLUME, OUTPUT_PLANTS, ROI
        r_plants = r_plants.json()
        PLANTS_PRICES = r_plants["buy_price"]
        OWNED_PLANTS = r_plants["power_plants_owned"]
        POWERED_PLANTS = r_plants["power_plants_powered"]
        PLANT_SELL_PRICES = r_plants["sell_price"]

        DATASET = [v for v in r_dataset.json().values()][0]
        for key, value in DATASET["power_plants_output"].items():
            OUTPUT_PLANTS[key].append(value)

        ROI = {key: roi(value, PLANTS_PRICES[key]) for key, value in OUTPUT_PLANTS.items()}

        ORDERS = r_orders.json()

        MONEY = r_player.json()["money"]
        CURRENT_VOLUME = r_player.json()["resources"]

        MATCHED_TRADES = r_matched_trades.json()

        logger.debug(f"Money: {MONEY}")
        logger.debug(f"Matched trades: {MATCHED_TRADES}")
        logger.debug(f"Outputs {OUTPUT_PLANTS}")
        logger.debug(f"Roi {ROI}")


def get_energy_price() -> float:
    return DATASET["max_energy_price"] * ENERGY_DISCOUNT


def check_if_power_plant_running(api: AlgotradeApi, resource: Resource):
    global MONEY

    if OWNED_PLANTS[resource.value] == 0:
        if MONEY < PLANTS_PRICES[resource.value]:
            logger.debug(f"Not enough money to buy {resource.value} plant")
            return False
        else:
            MONEY -= PLANTS_PRICES[resource.value]
            r = api.buy_plant(resource.value)
            logger.debug(f"Buying {resource.value} plant, response: {r.text}")
    if POWERED_PLANTS[resource.value] == 0:
        r = api.turn_on(resource.value, 1)
        logger.debug(f"Turning on {resource.value} plant, response: {r.text}")

    return True


def asset_arbitrage(api: AlgotradeApi, resource: Resource):
    energy_price = get_energy_price()  # max energy price
    if resource.value not in ORDERS:
        logger.debug(f"No orders for {resource.value}")
        return
    if "sell" not in ORDERS[resource.value]:
        logger.debug(f"No sell orders for {resource.value}")
        return
    resource_price = ORDERS[resource.value]["sell"]
    resource_price = sorted(resource_price, key=lambda x: x["price"])

    logger.debug(f"Energy price: {energy_price}")
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

            r = api.create_order(
                resource=resource.value,
                price=resource_price[i]["price"] * (1 + BUY_MARGIN),
                size=min(
                    resource_price[i]["size"] * OWNED_PLANTS[resource.value] * 2,
                    OWNED_PLANTS[resource.value] * 2,
                ),
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
                f"Buying {resource.value} price: {resource_price[i]['price'] * (1 + BUY_MARGIN)}, size: {resource_price[i]['size']}, response: {r.text}"
            )

        break

def roi(output_list_plants, plants_price):
    mean_output = sum(output_list_plants) / len(output_list_plants)
    roi = mean_output  / plants_price
    return roi


def on_tick_end(api: AlgotradeApi):
    pass


def tick():
    # Get current player stats

    on_tick_start(api)
    for resource in Resource:
        if resource.value in UNRENOVABLE:
            asset_arbitrage(api, resource)


if __name__ == "__main__":
    run_with_inputs()
