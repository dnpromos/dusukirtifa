from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🤖 AI Asistan", callback_data="ai_chat")],
        [InlineKeyboardButton("➕ Uçuş Takip Et", callback_data="track")],
        [InlineKeyboardButton("📋 Takip Listem", callback_data="list")],
        [InlineKeyboardButton("📈 Fiyat Trendleri", callback_data="trends")],
        [InlineKeyboardButton("✈️ Aktarmasız Uçuşlar", callback_data="direct")],
        [InlineKeyboardButton("🌍 Popüler Rotalar", callback_data="popular")],
        [InlineKeyboardButton("📊 Detaylı İstatistikler", callback_data="stats")],
        [InlineKeyboardButton("❌ Takibi Kaldır", callback_data="remove")],
    ])


def post_track_keyboard(flight_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("� Bu Uçuşun Trendleri", callback_data=f"trend_{flight_id}")],
        [InlineKeyboardButton("📊 Detaylı İstatistikler", callback_data="stats")],
        [InlineKeyboardButton("➕ Başka Uçuş Ekle", callback_data="track")],
        [InlineKeyboardButton("🔙 Ana Menü", callback_data="menu")],
    ])


def cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 İptal", callback_data="cancel")],
    ])


def flight_remove_keyboard(flights: list[dict]) -> InlineKeyboardMarkup:
    buttons = []
    for f in flights:
        label = f"{f['origin']} → {f['destination']} ({f['depart_date']})"
        buttons.append(
            [InlineKeyboardButton(f"❌ {label}", callback_data=f"rm_{f['id']}")]
        )
    buttons.append([InlineKeyboardButton("🔙 Ana Menü", callback_data="menu")])
    return InlineKeyboardMarkup(buttons)


def flight_trend_keyboard(flights: list[dict]) -> InlineKeyboardMarkup:
    buttons = []
    for f in flights:
        label = f"{f['origin']} → {f['destination']} ({f['depart_date']})"
        buttons.append(
            [InlineKeyboardButton(f"📈 {label}", callback_data=f"trend_{f['id']}")]
        )
    buttons.append([InlineKeyboardButton("🔙 Ana Menü", callback_data="menu")])
    return InlineKeyboardMarkup(buttons)


def flight_direct_keyboard(flights: list[dict]) -> InlineKeyboardMarkup:
    buttons = []
    for f in flights:
        label = f"{f['origin']} → {f['destination']} ({f['depart_date']})"
        buttons.append(
            [InlineKeyboardButton(f"✈️ {label}", callback_data=f"direct_{f['id']}")]
        )
    buttons.append([InlineKeyboardButton("🔙 Ana Menü", callback_data="menu")])
    return InlineKeyboardMarkup(buttons)


def back_to_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Ana Menü", callback_data="menu")],
    ])
