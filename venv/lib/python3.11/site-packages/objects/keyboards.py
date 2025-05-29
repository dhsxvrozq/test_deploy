from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

menu_was_trial = InlineKeyboardMarkup(inline_keyboard=[ 
    [InlineKeyboardButton(text="💳 Оплата", callback_data="payment")],
    [InlineKeyboardButton(text="ℹ Информация", callback_data="info")],
    [InlineKeyboardButton(text="💰 Цены", callback_data="prices")],
    # [InlineKeyboardButton(text="🤝 Рефералы", callback_data="referrals"),InlineKeyboardButton(text="🏷 Скидки", callback_data="discounts")],
    # [InlineKeyboardButton(text="🎁 Подарки", callback_data="gifts"),InlineKeyboardButton(text="📋 Транзакции", callback_data="transactions")],
    ])

menu_inactive_subscription = InlineKeyboardMarkup(inline_keyboard=[ 
    [InlineKeyboardButton(text="💳 Оплата", callback_data="payment")],
    [InlineKeyboardButton(text="ℹ Тест деплой", callback_data="test_deploy")],
    [InlineKeyboardButton(text="ℹ Информация", callback_data="info")],
    [InlineKeyboardButton(text="💰 Цены", callback_data="prices")],
    # [InlineKeyboardButton(text="🤝 Рефералы", callback_data="referrals"),InlineKeyboardButton(text="🏷 Скидки", callback_data="discounts")],
    # [InlineKeyboardButton(text="🎁 Подарки", callback_data="gifts"),InlineKeyboardButton(text="📋 Транзакции", callback_data="transactions")],
    [InlineKeyboardButton(text="🎁 Тест", callback_data="get_trial_subscription")],
    ])


menu_active_subscription = InlineKeyboardMarkup(inline_keyboard=[ 
    [InlineKeyboardButton(text="💳 Оплата", callback_data="payment")],
    [InlineKeyboardButton(text="ℹ Информация", callback_data="info")],
    [InlineKeyboardButton(text="💰 Цены", callback_data="prices")],
    # [InlineKeyboardButton(text="🤝 Рефералы", callback_data="referrals"),InlineKeyboardButton(text="🏷 Скидки", callback_data="discounts")],
    # [InlineKeyboardButton(text="🎁 Подарки", callback_data="gifts"),InlineKeyboardButton(text="📋 Транзакции", callback_data="transactions")],
    [InlineKeyboardButton(text="🎁 Подписка", callback_data="subscription_info")]
    ])

payment = InlineKeyboardMarkup(inline_keyboard=[ 
    [InlineKeyboardButton(text='1 месяц', callback_data= 'get_new_key')],
    [InlineKeyboardButton(text='3 месяца', callback_data= 'get_new_key')],
    [InlineKeyboardButton(text='6 месяцев', callback_data= 'get_new_key')],
    [InlineKeyboardButton(text='12 месяцев', callback_data= 'get_new_key')],
    [InlineKeyboardButton(text='↩️ Главное меню', callback_data= 'menu')]
    ])

info = InlineKeyboardMarkup(inline_keyboard=[ 
    [InlineKeyboardButton(text='Инструкция', callback_data= 'tutorial')],
    [InlineKeyboardButton(text='📜 Правила', callback_data= 'rules')],
    [InlineKeyboardButton(text='↩️ Главное меню', callback_data= 'menu')]
    ])


back_to_menu = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text='↩️ Главное меню', callback_data= 'menu')]
    ])