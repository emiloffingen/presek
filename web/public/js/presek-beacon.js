/* presek-beacon: one tiny pageview ping per real browser page load.
 * Privacy-friendly: server hashes IP+UA, stores no raw IP. */
(function () {
  try {
    if (document.prerendering) return;
    var ua = navigator.userAgent || '';
    if (/bot|crawl|spider|slurp|mediapartners|healthcheck/i.test(ua)) return;
    var payload = JSON.stringify({
      path: location.pathname.slice(0, 512),
      lang: (document.documentElement.lang || '').slice(0, 10),
      referrer: (document.referrer || '').slice(0, 512),
    });
    var url = '/api/stats/beacon';
    if (navigator.sendBeacon) {
      var blob = new Blob([payload], { type: 'application/json' });
      navigator.sendBeacon(url, blob);
    } else {
      fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: payload,
        keepalive: true,
        credentials: 'same-origin',
      }).catch(function () {});
    }
  } catch (e) {
    /* never break the page for analytics */
  }
})();
