# -----------------------------------------------------------------------------
# List of pages this feed builder checks for new publications.
#
# Every Irish government department now publishes through gov.ie, but each
# department also has its OWN publications listing (e.g.
# gov.ie/en/department-of-transport/publications/) which sometimes includes
# items that haven't (yet, or ever) been surfaced on the central
# gov.ie/en/publications/ aggregator. So we check both.
#
# One department -- Enterprise, Tourism and Employment -- still runs a
# genuinely separate website (enterprise.gov.ie) rather than a gov.ie section,
# so it's listed separately below with its own URL pattern.
#
# Feel free to add more rows here (e.g. specific agencies like the HSE,
# Central Bank, Revenue) -- just give each one a name and a listing URL that
# is sorted newest-first.
# -----------------------------------------------------------------------------

GOVIE_BASE = "https://www.gov.ie"

# The central aggregator. Catches most things, across every department.
CENTRAL_SOURCES = [
    {
        "name": "gov.ie – Publications (all departments)",
        "url": f"{GOVIE_BASE}/en/publications/?sort_by=published_date",
        "base": GOVIE_BASE,
    },
]

# Every individual department's own publications listing on gov.ie.
DEPARTMENT_SLUGS = {
    "Department of Agriculture, Food and the Marine": "department-of-agriculture-food-and-the-marine",
    "Department of Children, Disability and Equality": "department-of-children-disability-and-equality",
    "Department of Climate, Energy and the Environment": "department-of-climate-energy-and-the-environment",
    "Department of Culture, Communications and Sport": "department-of-culture-communications-and-sport",
    "Department of Defence": "department-of-defence",
    "Department of Education and Youth": "department-of-education",
    "Department of Finance": "department-of-finance",
    "Department of Foreign Affairs and Trade": "department-of-foreign-affairs",
    "Department of Further and Higher Education, Research, Innovation and Science": "department-of-further-and-higher-education-research-innovation-and-science",
    "Department of Health": "department-of-health",
    "Department of Housing, Local Government and Heritage": "department-of-housing-local-government-and-heritage",
    "Department of Justice, Home Affairs and Migration": "department-of-justice-home-affairs-and-migration",
    "Department of Public Expenditure, Infrastructure, Public Service Reform and Digitalisation": "department-of-public-expenditure-infrastructure-public-service-reform-and-digitalisation",
    "Department of Rural and Community Development and the Gaeltacht": "department-of-rural-and-community-development-and-the-gaeltacht",
    "Department of Social Protection": "department-of-social-protection",
    "Department of the Taoiseach": "department-of-the-taoiseach",
    "Department of Transport": "department-of-transport",
    # Enterprise, Tourism and Employment is handled separately below --
    # it's an EXTERNAL_SOURCE, not a gov.ie section.
}

DEPARTMENT_SOURCES = [
    {
        "name": name,
        "url": f"{GOVIE_BASE}/en/{slug}/publications/?sort_by=published_date",
        "base": GOVIE_BASE,
    }
    for name, slug in DEPARTMENT_SLUGS.items()
]

# Departments/agencies that publish on a genuinely separate domain rather
# than a gov.ie section. Add more here as you find them.
EXTERNAL_SOURCES = [
    {
        "name": "Department of Enterprise, Tourism and Employment",
        "url": "https://enterprise.gov.ie/en/publications/",
        "base": "https://enterprise.gov.ie",
    },
]

ALL_SOURCES = CENTRAL_SOURCES + DEPARTMENT_SOURCES + EXTERNAL_SOURCES
