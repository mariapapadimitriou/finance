"""Assign a spending category to each transaction.

Three layers, in priority order:

1. A user override for that exact merchant  (you told us once, we remember)
2. Pattern rules below                       (merchant name / raw descriptor)
3. The issuer's own category, loosely mapped (Chase and Amex both ship one)

Anything still unmatched lands in "Other", which the UI surfaces so you can
teach it — a correction there becomes a layer-1 override for every future row.
"""

from __future__ import annotations

import re

# ── Category vocabulary ──────────────────────────────────────────────────────
# `essential` drives the fixed-vs-discretionary split in the overview, and
# `discretionary` marks the categories the savings engine is allowed to
# suggest trimming. Transfers/Income are excluded from spending totals.
#
# Deliberately no per-category colour: there are far more categories here than
# any palette can keep distinguishable, and charts that cycle hues past about
# eight stop encoding anything. Category identity is carried by its label; the
# charts encode magnitude with a single hue.

CATEGORIES: dict[str, dict] = {
    "Groceries":        {"essential": True,  "discretionary": False},
    "Dining":           {"essential": False, "discretionary": True},
    "Food Delivery":    {"essential": False, "discretionary": True},
    "Coffee":           {"essential": False, "discretionary": True},
    "Alcohol & Bars":   {"essential": False, "discretionary": True},
    "Transport":        {"essential": True,  "discretionary": True},
    "Gas & Fuel":       {"essential": True,  "discretionary": False},
    "Travel":           {"essential": False, "discretionary": True},
    "Lodging":          {"essential": False, "discretionary": True},
    "Shopping":         {"essential": False, "discretionary": True},
    "Streaming":        {"essential": False, "discretionary": True},
    "News & Media":     {"essential": False, "discretionary": True},
    "Software":         {"essential": False, "discretionary": True},
    "Utilities":        {"essential": True,  "discretionary": False},
    "Phone & Internet": {"essential": True,  "discretionary": False},
    "Rent & Housing":   {"essential": True,  "discretionary": False},
    "Insurance":        {"essential": True,  "discretionary": False},
    "Health":           {"essential": True,  "discretionary": False},
    "Fitness":          {"essential": False, "discretionary": True},
    "Personal Care":    {"essential": False, "discretionary": True},
    "Entertainment":    {"essential": False, "discretionary": True},
    "Education":        {"essential": True,  "discretionary": False},
    "Pets":             {"essential": True,  "discretionary": False},
    "Home":             {"essential": True,  "discretionary": True},
    "Gifts & Charity":  {"essential": False, "discretionary": True},
    "Fees & Interest":  {"essential": False, "discretionary": True},
    "Taxes":            {"essential": True,  "discretionary": False},
    "Cash & ATM":       {"essential": False, "discretionary": False},
    "Income":           {"essential": False, "discretionary": False},
    "Transfers":        {"essential": False, "discretionary": False},
    "Other":            {"essential": False, "discretionary": True},
}

# Categories that are money movement, not consumption. Excluded from spend.
NON_SPEND = {"Income", "Transfers"}


def is_spend_category(category: str) -> bool:
    return category not in NON_SPEND


def is_discretionary(category: str) -> bool:
    return CATEGORIES.get(category, {}).get("discretionary", False)


# ── Pattern rules ────────────────────────────────────────────────────────────
# Ordered: the first match wins, so put specific merchants above generic words.
# Patterns are matched case-insensitively against "MERCHANT || raw description".

RULES: list[tuple[str, str]] = [
    # Fees & interest first — these are the highest-value findings and their
    # descriptors often contain a merchant word that would otherwise capture them.
    (r"\b(interest charge|purchase interest|cash advance fee|finance charge)\b", "Fees & Interest"),
    (r"\b(late fee|overlimit fee|over-limit|nsf fee|returned payment)\b", "Fees & Interest"),
    (r"\b(annual (membership )?fee|membership fee|card fee)\b", "Fees & Interest"),
    (r"\b(foreign transaction fee|forex fee|fx fee|non-sterling|conversion fee)\b", "Fees & Interest"),
    (r"\b(atm fee|service charge|monthly fee|maintenance fee|overdraft)\b", "Fees & Interest"),

    # Payments & transfers
    # Card payments come in many spellings; all of them are money moving onto
    # the card, never a purchase. Missing one silently nets it against your
    # spending and makes the month look almost free.
    (r"\b(payment thank you|payment received|payment from|payment -|autopay|"
     r"online payment|pre-?authorized payment|pmt thank you)\b", "Transfers"),
    (r"\b(scene\+? points|points for credit|rewards? redemption|"
     r"cash ?back redemption|credit bal(?:ance)? refund)\b", "Transfers"),
    (r"\b(e-?transfer|interac|zelle|venmo|wise|remitly|western union)\b", "Transfers"),
    (r"\b(transfer to|transfer from|internal transfer|balance transfer)\b", "Transfers"),
    (r"\b(payroll|direct deposit|salary|dep\s+payroll|refund)\b", "Income"),

    # Coffee
    (r"\b(starbucks|blue bottle|peet'?s|tim hortons|dunkin|philz|intelligentsia|"
     r"caribou coffee|second cup|coffee|cafe|espresso|roasters)\b", "Coffee"),

    # Food delivery — must precede Dining, the merchants overlap.
    (r"\b(uber\s*eats|doordash|door dash|grubhub|seamless|postmates|skip\s*the\s*dishes|"
     r"skipthedishes|deliveroo|just eat|instacart|gopuff|caviar|foodora)\b", "Food Delivery"),

    # Groceries
    (r"\b(whole foods|trader joe|safeway|kroger|publix|aldi|lidl|wegmans|heb|"
     r"h-e-b|sprouts|ralphs|vons|albertsons|food lion|giant eagle|stop & shop|"
     r"loblaws|metro|sobeys|no frills|save on foods|fortinos|freshco|iga|"
     r"superstore|farm boy|costco|sam'?s club|grocer|supermarket|market basket)\b", "Groceries"),

    # Alcohol
    (r"\b(lcbo|saq|beer store|total wine|bevmo|liquor|winery|brewery|brewing|"
     r"tavern|pub|cocktail|distillery|bar|taproom|wine shop|saloon)\b",
     "Alcohol & Bars"),

    # Dining
    (r"\b(restaurant|grill|kitchen|bistro|pizzeria|pizza|sushi|taco|burger|"
     r"noodle|ramen|thai|bbq|steakhouse|diner|deli|bakery|chipotle|sweetgreen|"
     r"mcdonald|wendy|subway sandwich|panera|shake shack|five guys|popeyes|"
     r"kfc|taco bell|dominos|papa john|olive garden|cheesecake factory|nando)\b", "Dining"),

    # Rideshare / transit
    (r"\b(uber(?!\s*eats)|lyft|bolt|via transportation|taxi|cab co)\b", "Transport"),
    (r"\b(mta|bart|caltrain|amtrak|ttc|presto|go transit|via rail|metro transit|"
     r"transit authority|subway fare|parking|park\s*mobile|spothero|impark|"
     r"green p|toll|fastrak|407 etr)\b", "Transport"),

    # Fuel
    (r"\b(shell|chevron|exxon|mobil|bp |texaco|arco|petro-?canada|esso|husky|"
     r"circle k|speedway|sunoco|citgo|marathon petro|gas station|fuel)\b", "Gas & Fuel"),

    # Travel & lodging
    (r"\b(marriott|hilton|hyatt|sheraton|westin|holiday inn|best western|"
     r"airbnb|vrbo|booking\.com|hotels\.com|expedia|hostel|motel|inn\b)\b", "Lodging"),
    (r"\b(air canada|united airlines|delta air|american airlines|westjet|"
     r"southwest air|jetblue|alaska air|porter airlines|lufthansa|british airways|"
     r"air france|klm|emirates|airline|airways|flight|kayak|priceline|"
     r"travelocity|trip\.com|rental car|hertz|avis|enterprise rent|budget rent)\b", "Travel"),

    # Streaming & entertainment
    (r"\b(netflix|spotify|hulu|disney\+?|disneyplus|hbo|max\.com|paramount\+?|"
     r"peacock|apple tv|apple music|youtube premium|youtube tv|crave|prime video|"
     r"audible|tidal|deezer|sirius\s*xm|curiositystream|mubi)\b", "Streaming"),
    (r"\b(nytimes|new york times|wall street journal|wsj|washington post|"
     r"the atlantic|the economist|globe and mail|financial times|bloomberg\.com|"
     r"substack|medium\.com|the guardian|reuters|newspaper|magazine)\b", "News & Media"),
    (r"\b(amc |cinemark|regal cinema|cineplex|landmark theat|movie|theatre|theater|"
     r"ticketmaster|stubhub|eventbrite|live nation|steam games|steampowered|"
     r"playstation|xbox|nintendo|epic games|twitch|patreon)\b", "Entertainment"),

    # Software & services
    (r"\b(adobe|microsoft|office 365|google (one|storage|workspace)|dropbox|"
     r"notion|figma|slack|zoom\.us|github|gitlab|jetbrains|1password|lastpass|"
     r"nordvpn|expressvpn|squarespace|wix|godaddy|namecheap|cloudflare|"
     r"digitalocean|linode|heroku|vercel|netlify|openai|anthropic|claude|"
     r"chatgpt|midjourney|canva|grammarly|evernote|todoist|amazon web services|aws)\b",
     "Software"),
    (r"\b(apple\.com/bill|itunes|app store|google play|amazon prime)\b", "Software"),

    # Fitness & health
    (r"\b(gym|fitness|planet fitness|equinox|goodlife|la fitness|crossfit|"
     r"orangetheory|f45|peloton|classpass|yoga|pilates|climbing)\b", "Fitness"),
    (r"\b(pharmacy|cvs|walgreens|rite aid|shoppers drug|rexall|london drugs|"
     r"clinic|dental|dentist|doctor|medical|hospital|optometr|physio|"
     r"chiropract|therapy|lab ?corp|quest diagnostics)\b", "Health"),

    # Personal care
    (r"\b(salon|barber|spa\b|nails|sephora|ulta|haircut|aesthetic|massage)\b", "Personal Care"),

    # Utilities / telecom / housing
    (r"\b(hydro|electric|power co|pg&e|con ?edison|duke energy|national grid|"
     r"water dept|waste management|gas company|enbridge|fortis|utility)\b", "Utilities"),
    (r"\b(at&t|verizon|t-?mobile|sprint|rogers|bell canada|telus|fido|koodo|"
     r"freedom mobile|comcast|xfinity|spectrum|cox comm|shaw|videotron|"
     r"internet|wireless|mobile bill)\b", "Phone & Internet"),
    (r"\b(rent |landlord|property mgmt|property management|mortgage|strata|"
     r"condo fee|hoa )\b", "Rent & Housing"),
    (r"\b(insurance|geico|state farm|progressive|allstate|intact|aviva|"
     r"belairdirect|sun life|manulife)\b", "Insurance"),

    # Shopping & home
    (r"\b(home depot|lowe'?s|rona|canadian tire|ikea|wayfair|bed bath|"
     r"hardware|garden cent|ace hardware)\b", "Home"),
    (r"\b(amazon|walmart|target|best buy|costco wholesale|ebay|etsy|shein|"
     r"temu|aliexpress|zara|h&m|uniqlo|nordstrom|macy'?s|gap |old navy|"
     r"lululemon|nike|adidas|foot locker|winners|marshalls|tj ?maxx|"
     r"hudson'?s bay|sport chek|mec\b|rei\b|apple store)\b", "Shopping"),

    # ── Toronto & Canada ─────────────────────────────────────────────────────
    # Local independents dominate a real Canadian statement and none of the
    # chain lists above touch them. Ordered before the generic rules so a
    # specific venue wins over a stray keyword in its name.

    (r"\b(bike share toronto|presto|ttc|go transit|via rail|up express)\b|\bomny",
     "Transport"),
    (r"\b(sweat and tonic|altea|f45|barry'?s bootcamp|spinco|orangetheory)\b",
     "Fitness"),
    (r"\b(shoppers dru|rexall|pharmaprix|duane reade|cvs)\b", "Health"),
    (r"\b(rabba|longo'?s|farm boy|fortinos|freshco|food basics|galleria|"
     r"little harvest market|world mart)\b", "Groceries"),
    (r"\b(simons|dynamite|garage|victoria'?s secret|urban outfitters|"
     r"ralph lauren|vintage twin|aritzia|roots canada|sporting life|"
     r"hudson'?s bay|the bay street)\b|\burbanoutfitters",
     "Shopping"),
    (r"\b(olfactory|sephora|deciem|the ordinary)\b", "Personal Care"),
    (r"\b(scotiabank arena|scotiabank north|ca wonderland|canada'?s wonderland|"
     r"metropolitan museum|rendezviews|stackt market|ripley'?s)\b",
     "Entertainment"),
    (r"\b(moxy|the drake hotel|gladstone)\b", "Lodging"),
    # No trailing \\b: these appear glued to other words in card descriptors
    # ("CAPITALIZEFORKIDSFOUND", "WWW.URBANOUTFITTERS.CO", "OMNYPYG").
    (r"\b(capitalizeforkids|children'?s (?:aid|wish)|sickkids|united way)",
     "Gifts & Charity"),

    # Coffee shops — %Arabica and the local roasters.
    (r"(%\s*)?\barabica\b|\b(mos mos|dineen|neo coffee|a-ok cafe|cha cha matcha|"
     r"the roasted nut|boxcar social|jimmy'?s coffee|dark horse)\b", "Coffee"),
    (r"\bcafe\d*\b|\bcaf[ée]\b", "Coffee"),

    # Bars & nightlife
    (r"\b(king taps|dream baby|cherry'?s high dive|locals only|central taps|"
     r"hooters|the well bar|apres ski)\b", "Alcohol & Bars"),

    # Restaurants, food halls and the quick-service places that make up most
    # of a downtown lunch habit.
    (r"\b(locanda verde|anejo|zen kyoto|nutbar|soup nutsy|iq food|azul|chop hop|"
     r"pumpernickels|z-?teca|miznon|poulet rouge|villa madina|olly frescos|"
     r"big league food|patties express|freshly squeezed|booster juice|"
     r"craig'?s cookies|black seed|time out market|urban backyard|ruby soho|"
     r"local adelaide|grand bizzare|aera|daon|haydn'?s|nord lyon|vereda|"
     r"columbus eaton|queen'?s cross|chefs hall|rosie'?s burgers|belly busters|"
     r"the agora|mandys|impact kitchen|peter pan bistro|national bowl|"
     r"bowery bay|shg -|lcc toronto)\b", "Dining"),
    # Generic food-service words, last so a named venue above wins first.
    (r"\b(food hall|food co|foods|bowl|bagel|cookie|juice|matcha|soup|"
     r"taps|cocina|bistro|taverna|creamery|patisserie)\b", "Dining"),


    (r"\b(petsmart|petco|pet valu|chewy|veterinar|vet clinic|animal hospital)\b", "Pets"),
    (r"\b(tuition|university|college|coursera|udemy|skillshare|masterclass|"
     r"duolingo|textbook|student loan)\b", "Education"),
    (r"\b(gofundme|red cross|unicef|donation|charity|church)\b", "Gifts & Charity"),
    (r"\b(irs |cra |tax payment|revenue service|turbotax|h&r block)\b", "Taxes"),
    (r"\b(atm withdrawal|cash withdrawal|cash advance|abm withdrawal)\b", "Cash & ATM"),
]

_COMPILED = [(re.compile(p, re.I), cat) for p, cat in RULES]

# The issuer's own label, when we have nothing better to go on.
ISSUER_CATEGORY_MAP = {
    "food & drink": "Dining",
    "restaurants": "Dining",
    "restaurant": "Dining",
    "dining": "Dining",
    "groceries": "Groceries",
    "supermarkets": "Groceries",
    "merchandise & supplies": "Shopping",
    "shopping": "Shopping",
    "entertainment": "Entertainment",
    "travel": "Travel",
    "transportation": "Transport",
    "gas": "Gas & Fuel",
    "gasoline": "Gas & Fuel",
    "automotive": "Transport",
    "bills & utilities": "Utilities",
    "utilities": "Utilities",
    "health & wellness": "Health",
    "medical": "Health",
    "personal": "Personal Care",
    "fees & adjustments": "Fees & Interest",
    "fees": "Fees & Interest",
    "payment": "Transfers",
    "payments": "Transfers",
    "transfer": "Transfers",
    "income": "Income",
    "education": "Education",
    "insurance": "Insurance",
    "home": "Home",
    "professional services": "Other",
}


def categorize(merchant: str, description: str = "", issuer_category: str = "",
               overrides: dict[str, str] | None = None) -> tuple[str, str]:
    """Return (category, source) for one transaction."""
    key = (merchant or "").strip().lower()

    if overrides and key in overrides:
        return overrides[key], "merchant_override"

    haystack = f"{merchant} || {description}"
    for pattern, category in _COMPILED:
        if pattern.search(haystack):
            return category, "rule"

    if issuer_category:
        mapped = ISSUER_CATEGORY_MAP.get(issuer_category.strip().lower())
        if mapped:
            return mapped, "issuer"
        # Plaid ships SCREAMING_SNAKE detail codes; try the leading segment.
        head = issuer_category.split("_")[0].replace("-", " ").strip().lower()
        mapped = ISSUER_CATEGORY_MAP.get(head)
        if mapped:
            return mapped, "issuer"

    return "Other", "rule"


def apply_categories(transactions, overrides: dict[str, str] | None = None) -> None:
    """Categorize in place, leaving explicit user choices untouched."""
    for t in transactions:
        if t.category and t.category_source == "user":
            continue
        issuer_cat = (t.raw or {}).get("issuer_category", "")
        t.category, t.category_source = categorize(
            t.merchant, t.description, issuer_cat, overrides
        )
