// Vercel serverless proxy: live availability/price check for one Villa Finder public listing.
// GET /api/offer?slug=<villa-slug>&from=YYYY-MM-DD&to=YYYY-MM-DD
module.exports = async (req, res) => {
  const { slug = '', from = '', to = '' } = req.query || {};
  if (!/^[a-z0-9-]{2,80}$/.test(slug) || !/^\d{4}-\d{2}-\d{2}$/.test(from) || !/^\d{4}-\d{2}-\d{2}$/.test(to)) {
    res.status(400).json({ error: 'bad params' });
    return;
  }
  const url = `https://www.villa-finder.com/en/api/offer/${slug}.json?host=www.villa-finder.com&from=${from}&to=${to}`;
  try {
    const r = await fetch(url, {
      headers: {
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'en-US,en;q=0.9',
        'Referer': `https://www.villa-finder.com/en/villa/${slug}?from=${from}&to=${to}`,
        'Origin': 'https://www.villa-finder.com',
        'Sec-Fetch-Dest': 'empty', 'Sec-Fetch-Mode': 'cors', 'Sec-Fetch-Site': 'same-origin',
        'X-Requested-With': 'XMLHttpRequest',
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36',
      },
    });
    const text = await r.text();
    res.setHeader('Cache-Control', 's-maxage=120, stale-while-revalidate=600');
    res.setHeader('Content-Type', 'application/json; charset=utf-8');
    if (!r.ok) { res.status(r.status === 429 ? 429 : 502).send(JSON.stringify({ error: 'upstream ' + r.status, cf: r.headers.get('cf-mitigated') || r.headers.get('server') || '', body: text.slice(0, 200) })); return; }
    res.status(200).send(text);
  } catch (e) {
    res.status(502).json({ error: String(e && e.message || e) });
  }
};
