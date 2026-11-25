from eras import ERAS


RARITIES = {
    "Common": 100000,
    "Rare": 44203,
    "Epic": 580,
    "Legendary": 10,
    "Mythic": 1,
}
SPIN_DAILY_LIMIT = 5
SPIN_REWARD_COUNTS = {
    "Common": {
        "Common": 8,
        "Rare": 4,
        "Epic": 2,
        "Legendary": 1,
        "Mythic": 0,
    },
    "Rare": {
        "Common": 6,
        "Rare": 4,
        "Epic": 3,
        "Legendary": 2,
        "Mythic": 0,
    },
    "Epic": {
        "Common": 5,
        "Rare": 4,
        "Epic": 3,
        "Legendary": 2,
        "Mythic": 1,
    },
    "Legendary": {
        "Common": 3,
        "Rare": 3,
        "Epic": 4,
        "Legendary": 3,
        "Mythic": 2,
    },
    "Mythic": {
        "Common": 2,
        "Rare": 3,
        "Epic": 4,
        "Legendary": 4,
        "Mythic": 2,
    },
}
SPIN_BOMB_SLOTS = 1
SPIN_BOARD_SIZE = 16

S_ORDER = (
    "YSY", "JHR", "LJW", "KCY", "KYY", "KSM", "KNK", "GYB", "KAE", "SDH",
    "KTN", "KYJ", "HST", "PSH", "ZXY", "KMY", "LYN", "JBN", "JHY", "SHI",
    "KCW", "SUL", "SEO", "JSH",
)
S_MEMBERS = {
    code: ERAS["ASSEMBLE"]["members"][code]
    for code in S_ORDER[:10]
}
S_MEMBERS.update({
    "KTN": {"name": "Kotone", "full_name": "Kamimoto Kotone"},
    "KYJ": {"name": "Yeonji", "full_name": "Kwak Yeonji"},
    "HST": {"name": "Nien", "full_name": "Hsu Nien Tzu"},
    "PSH": {"name": "Sohyun", "full_name": "Park Sohyun"},
    "ZXY": {"name": "Xinyu", "full_name": "Zhou Xinyu"},
    "KMY": {"name": "Mayu", "full_name": "Koma Mayu"},
    "LYN": {"name": "Lynn", "full_name": "Kawakami Lynn"},
    "JBN": {"name": "Joobin", "full_name": "Joo Bin"},
    "JHY": {"name": "Hayeon", "full_name": "Jeong Hayeon"},
    "SHI": {"name": "Shion", "full_name": "Park Shion"},
    "KCW": {"name": "Chaewon", "full_name": "Kim Chaewon"},
    "SUL": {"name": "Sullin", "full_name": "Pirada Bunraksa"},
    "SEO": {"name": "Seoah", "full_name": "Jeong Haerin"},
    "JSH": {"name": "Jiyeon", "full_name": "Ji Suhyeon"},
})
MEMBER_SPECIALTY = {
    "YSY": "Vocals",
    "JHR": "Dance",
    "LJW": "Vocals",
    "KCY": "Vocals",
    "KYY": "Vocals",
    "KSM": "Vocals",
    "KNK": "Rap",
    "GYB": "Dance",
    "KAE": "Dance",
    "SDH": "Vocals",
    "KTN": "Rap",
    "KYJ": "Dance",
    "HST": "Rap",
    "PSH": "Rap",
    "ZXY": "Dance",
    "KMY": "Vocals",
    "LYN": "Dance",
    "JBN": "Vocals",
    "JHY": "Vocals",
    "SHI": "Vocals",
    "KCW": "Vocals",
    "SUL": "Dance",
    "SEO": "Vocals",
    "JSH": "Dance",
}
RARITY_ABILITY_ROLLS = {
    "Common": {"specialty": (10, 15), "cap": 40},
    "Rare": {"specialty": (15, 25), "cap": 60},
    "Epic": {"specialty": (26, 42), "cap": 85},
    "Legendary": {"specialty": (44, 66), "cap": 115},
    "Mythic": {"specialty": (68, 92), "cap": 150},
}
TRAIN_COOLDOWN_SECONDS = 4 * 60 * 60
TRAIN_GAIN_MIN = 3
TRAIN_GAIN_MAX = 6
TRAIN_PERFECT_CHANCE = 0.1
TRAIN_PERFECT_BONUS = 3
PERFORM_COOLDOWN_SECONDS = 4 * 60 * 60
HUNT_COOLDOWN_SECONDS = 4 * 60 * 60
HUNT_COMO_REWARDS = {
    "Common": (20, 35),
    "Rare": (35, 60),
    "Epic": (70, 120),
    "Legendary": (140, 220),
    "Mythic": (250, 400),
}
PERFORM_BASE_SCORE = 25
PERFORM_SKILL_WEIGHT = 1.7
PERFORM_RARITY_MULTIPLIERS = {
    "Common": 1.0,
    "Rare": 1.08,
    "Epic": 1.2,
    "Legendary": 1.35,
    "Mythic": 1.55,
}
PERFORM_GRADE_MULTIPLIERS = {
    "C": 1.0,
    "B": 1.08,
    "A": 1.18,
    "S": 1.3,
}
MINIGAMES = (
    (
        "tripleS Trivia",
        "Answer tripleS trivia questions to earn COMO.",
        "/trivia",
    ),
    (
        "Card Hunt",
        "Send a card into the forest to find COMO and another card.",
        "/hunt",
    ),
)
