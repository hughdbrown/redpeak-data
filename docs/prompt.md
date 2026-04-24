# Project
This is a project to scrape public data from the websites of rental properties. The goal is to have an historical record of the listed rental prices for apartments.

# Approach
The project follows the outline in this blog for maintaining an historical data log using github for versioning the data:
https://simonwillison.net/2020/Oct/9/git-scraping/

# Stack
- python3
- requests (for HTTP requsts)
- click (for command line options)

# Operation
1. On a cron job, the script will be called to perform the scrape
2. The script will have a list of URLs to work on
3. For each URL:
3.1. Do an HTTP GET to retrieve property rental data
3.2. Strip out noise
3.3. Each line that remains is an apartment for rent at a property
3.4. Retrieve the available date, the apartment number, the price, number of bedrooms, space in square feet
3.5. Save to the data directory for that property, using this format: `<property-name>-<date>.txt`
3.6. If the previous file was identical (or there was none), delete the new file. Otherwise keep the file

# Github actions
The operation will be done launched by a Github action in `.github/workflows/scrape.yml`
It will work much like this one reference implementation:
`https://github.com/simonw/ca-fires-history/blob/main/.github/workflows/scrape.yml`
