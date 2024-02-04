from .exceptions import *
from .constants import *
from .levels import *
from .renderer import render
from .pets import Pet
import gzip
import base64
import struct
import asyncio
import aiohttp

def TAG_End(b):
    return None, b


def TAG_byte(b):
    return b[0], b[1:]


def TAG_Short(b):
    return struct.unpack('>h', b[:2])[0], b[2:]


def TAG_Short_unsigned(b):
    return struct.unpack('>H', b[:2])[0], b[2:]


def TAG_Int(b):
    return struct.unpack('>i', b[:4])[0], b[4:]


def TAG_Long(b):
    return struct.unpack('>q', b[:8])[0], b[8:]


def TAG_Float(b):
    return struct.unpack('>f', b[:4])[0], b[4:]


def TAG_Double(b):
    return struct.unpack('>d', b[:8])[0], b[8:]


def TAG_Byte_Array(b):
    length, b = TAG_Int(b)
    items = []
    for _ in range(length):
        item, b = TAG_byte(b)
        items.append(item)
    decomp = gzip.decompress(bytes(items))
    return TAG_Compound(decomp)[0]['']['i'], b


def TAG_String(b):
    length, b = TAG_Short_unsigned(b)
    value = b[:length]
    b = b[length:]
    return value, b


def TAG_List(b, use_binary=False):
    tag_type, b = b[0], b[1:]
    length, b = TAG_Int(b)
    values = []
    for _ in range(length):
        if tag_type in (9, 10):
            value, b = tags[tag_type](b, use_binary=use_binary)
        else:
            value, b = tags[tag_type](b)
        values.append(value.decode('utf-8')
                      if isinstance(value, bytes) else value)
    return values, b


def TAG_Compound(b, use_binary=False):
    output = {}
    value = True
    while b:
        tag_type, b = TAG_byte(b)
        if tag_type == 0:
            break
        else:
            tag_name, b = TAG_String(b)
            if tag_type in (9, 10):
                value, b = tags[tag_type](b, use_binary=use_binary)
            else:
                value, b = tags[tag_type](b)
            if not use_binary:
                tag_name = tag_name.decode('utf-8')
            output[tag_name] = value.decode(
                'utf-8') if isinstance(value, bytes) else value
    return output, b


def TAG_Int_Array(b):
    pass


def TAG_Long_Array(b):
    pass


tags = (
    TAG_End,
    TAG_byte,
    TAG_Short,
    TAG_Int,
    TAG_Long,
    TAG_Float,
    TAG_Double,
    TAG_Byte_Array,
    TAG_String,
    TAG_List,
    TAG_Compound,
    TAG_Int_Array,
    TAG_Long_Array,
)


def decode_item(nbt):
    nbt = gzip.decompress(base64.b64decode(nbt))
    data = TAG_Compound(nbt)[0]

    return data


class Item:
    def __init__(self, data):

        self.count = data.get("Count", 1)

        tag = data.get("tag", {})
        display = tag.get("display", {})
        item_lore = display.get("Lore", [])
        item_name = display.get("Name", "")

        self.lore = []
        lore = [item_name, *item_lore]
        for line in lore:
            line = line.replace("§", "&")
            self.lore.append(line)

        attributes = tag.get("ExtraAttributes", {})
        self.hot_potato_count = attributes.get("hot_potato_count", 0)
        self.reforge = attributes.get("modifier", "")
        self.stars = attributes.get("upgrade_level", 0)
        self._id = attributes.get("id", "")
        self.enchantments = attributes.get("enchantments", {})
        self.item_uuid = attributes.get("uuid", "")

    def render(self):
        return render(self.lore)

class Profile:
    def __init__(self, profile_data, cute_name, uuid, api_key):
        self.profile_data_raw = profile_data
        self.cute_name = cute_name
        self.profile_id = None
        self.uuid = uuid
        self.networth_data = None
        self.bank_balance = 0
        self.museum_data = 0
        self.api_key = api_key

        for profile in profile_data["profiles"]:

            if profile["cute_name"] == cute_name:
                _profile = profile

        else:
            for profile in profile_data["profiles"]:
                if profile["selected"] is True:
                    _profile = profile
                    self.cute_name = profile["cute_name"]
                    break


        banking = _profile.get("banking", {})
        self.bank_balance = banking.get("balance", 0)
        self.profile_data_raw = _profile
        self.profile_id = _profile["profile_id"]
        self.profile_type = _profile.get("game_mode", "normal")

        if uuid in _profile["members"]:
            self.profile_data_user = _profile["members"][uuid]

        else:
            raise SkyblockParserException("User not in Profile")

        leveling = self.profile_data_user.get("leveling", {})
        self.skyblock_level = leveling.get("experience", 0) / 100

        self.collections = self.profile_data_user.get("collection", {})

        self.pets = []
        pet_data = self.profile_data_user.get("pets_data", [])
        for pet in pet_data.get("pets", []):
            self.pets.append(Pet(pet))

        if self.profile_data_user.get("rift", {}).get("dead_cats", {}).get("montezuma"):
            self.pets.append(
                Pet(self.profile_data_user["rift"]["dead_cats"]["montezuma"]))

        inventory = self.profile_data_user.get("inventory", {})
        self.sacks = inventory.get("sacks_counts", {})

        to_decode = [
            "inv",
            "ender_chest",
            "inv_armor",
            "wardrobe",
            "equipment",
            "personal_vault",
            "backpack"
        ]

        for item in to_decode:
            if item == "inv_armor":
                self.decode_items(inventory.get(item, {}).get("data", ""), item)

            elif item == "backpack":
                data = inventory.get(item + "_contents", {})
                for item in data:
                    page_data = data[item].get("data", "")
                    self.decode_items(page_data, f"backpack_{item}")

            else:
                self.decode_items(inventory.get(item + "_contents", {}).get("data", ""), item)

        self.backpack_count = len([x for x in dir(self) if "backpack_" in x])

        bags = inventory.get("bag_contents", {})
        for bag in bags:	
            data = bags[bag].get("data", "")
            self.decode_items(data, bag)

        self.bestiary = self.profile_data_user.get("bestiary", {})
        self.quests = self.profile_data_user.get("quests", {})
        self.nether = self.profile_data_user.get("nether_island_player_data", {})

        asyncio.run(self.get_museum())
        asyncio.run(self.get_stats())

    async def get_stats(self):
        await asyncio.gather(
            self.get_dungeon_stats(),
            self.get_slayer_stats(),
            self.get_skill_stats(),
            self.get_mining_stats(),
            self.get_general_stats(),
            self.get_networth()
        )

    def decode_items(self, nbt, _type):
        items = decode_item(nbt)[""]["i"]
        for item in items:
            if item.get("tag", {}).get("ExtraAttributes", {}).get("id", "") == "PET":
                self.pets.append(Pet(item["tag"], False))
                items.remove(item)
                continue

        setattr(self, _type, [Item(item) for item in items if item])

    async def get_museum(self):
        if self.museum_data is None:
            url = f"https://api.hypixel.net/v2/skyblock/museum?key={self.api_key}&profile={self.profile_id}"
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    data = await response.json()
                    self.museum_data = data["members"][self.uuid]

    async def get_networth(self):
        if self.networth_data is None:
            url = "https://nw-api.noms.tech/networth"
            body = {
                "profile": self.profile_data_user,
                "bank": self.bank_balance,
                "museumData": self.museum_data
            }
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=body) as response:
                    data = await response.json()
                    self.networth_data = data

    async def get_dungeon_stats(self):

        experience = self.profile_data_user.get("dungeons", {}).get(
            "dungeon_types", {}).get("catacombs", {}).get("experience", 0)
        level = get_cata_lvl(experience)

        classes = [
            "healer",
            "mage",
            "berserk",
            "archer",
            "tank"
        ]

        class_data = {_class: {} for _class in classes}

        for d_class in classes:
            d_class_data = self.profile_data_user.get("dungeons", {}).get(
                "player_classes", {}).get(d_class, {})

            class_xp = d_class_data.get("experience", 0)

            class_data[d_class]["experience"] = class_xp
            class_data[d_class]["level"] = get_cata_lvl(class_xp)

        dungeon_data = {
            "experience": experience,
            "level": level,
            "classes": class_data
        }
        self.dungeon_data = dungeon_data
        return

    async def get_slayer_stats(self):
        slayers = ["zombie", "spider", "wolf", "enderman", "blaze", "vampire"]
        slayer_data = {slayer: {} for slayer in slayers}

        for slayer in slayers:
            _slayer = self.profile_data_user.get(
                "slayer_bosses", {}).get(slayer, {})
            experience = _slayer.get("xp", 0)
            level = get_slayer_level(slayer, experience)
            slayer_data[slayer]["experience"] = experience
            slayer_data[slayer]["level"] = level

        slayer_data["raw"] = self.profile_data_user.get("slayer_bosses", {})

        self.slayer_data = slayer_data
        return

    async def get_skill_stats(self):
        skills = self.profile_data_user.get("player_data", {}).get("experience", {})
        skill_data = {}
        for skill in skills:
            formatted_skill_string = skill.replace("SKILL_", "").lower()
            exp = skills[skill]
            level = get_skill_lvl(formatted_skill_string, exp)
            skill_data[formatted_skill_string] = {
                "experience": exp,
                "level": level
            }

        self.skill_data = skill_data
        return
    
    async def get_mining_stats(self):
        mining_data = self.profile_data_user.get("mining_core", {})
        hotm_experience = mining_data.get("experience", 0)
        hotm_level = get_hotm_level(hotm_experience)

        powder = {
            "gemstone": {
                "available": mining_data.get("powder_gemstone", 0),
                "total": mining_data.get("powder_gemstone", 0) + mining_data.get("powder_spent_gemstone", 0)

            },
            "mithril": {
                "available": mining_data.get("powder_mithril", 0),
                "total": mining_data.get("powder_mithril_total", 0) + mining_data.get("powder_spent_mithril", 0)
            }
        }

        self.mining_data = {
            "forge": self.profile_data_user.get("forge", {}),
            "hotm": {
                "experience": hotm_experience,
                "level": hotm_level,
                "tokens": mining_data.get("tokens_spent", 0) + mining_data.get("tokens", 0),
                "tokens_spent": mining_data.get("tokens_spent", 0),
                "selected_ability": mining_data.get("selected_pickaxe_ability", ""),
                "powder": powder,
                "crystals": mining_data.get("crystals", {})
            }
        }

        return
    
    async def get_general_stats(self):
        player_stats = self.profile_data_user.get("player_stats", {})

        deaths = player_stats.get("deaths", 0)
        kills = player_stats.get("kills", 0)
        auctions = player_stats.get("auctions", {})
        end_island = player_stats.get("end_island", {})
        races = player_stats.get("races", {})
        pets = player_stats.get("pets", {})
        diana = player_stats.get("mythos", {})
        rift = player_stats.get("rift", {})

        winter = player_stats.get("winter", {})
        winter["gifts"] = player_stats.get("gifts", {})

        spooky_festival = player_stats.get("candy_collected", {})
        spooky = {
            "total": spooky_festival.get("total", 0),
            "green_candy": spooky_festival.get("green_candy", 0),
            "purple_candy": spooky_festival.get("purple_candy", 0),
            "bats_spawned": player_stats.get("sppoky", {}).get("bats_spawned", {}),
        }

        damages = {
            "highest_critical_damage": player_stats.get("highest_critical_damage", 0),
            "highest_damage": player_stats.get("highest_damage", 0),
        }

        fishing = {
            "items_fished": player_stats.get("items_fished", 0),
            "shredder": player_stats.get("shredder_rod", 0),
            "sea_creature_kills": player_stats.get("sea_creature_kills", 0),
            "trophy_fish": self.profile_data_user.get("trophy_fish", {})
        }

        faily_souls = self.profile_data_user.get("fairy_soul", {})

        self.general_stats = {
            "deaths": deaths,
            "kills": kills,
            "auctions": auctions,
            "end_island": end_island,
            "races": races,
            "pets": pets,
            "diana": diana,
            "rift": rift,
            "winter": winter,
            "spooky_festival": spooky,
            "damages": damages,
            "fishing": fishing,
            "fairy_souls": faily_souls
        }

        return

class SkyblockParser:
    """
    Use raw Hypixel API Data
    """

    def __init__(self, data, uuid, api_key):
        self.profiles = data
        self.uuid = uuid
        self.api_key = api_key

        if data.get("success") is False:
            reason = data.get("cause")
            raise SkyblockParserException(reason)

    def select_profile(self, cute_name):
        return Profile(self.profiles, cute_name, self.uuid, self.api_key)