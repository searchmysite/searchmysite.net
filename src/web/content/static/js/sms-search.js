// searchmysite.net embeddable search box
// Usage: <script src="https://searchmysite.net/static/js/sms-search.js" data-domain="example.com"></script>
// If the domain's listing has the API enabled (Free Trial or Full), a search box and
// results list are shown on the current page, using the site specific API.
// Otherwise (Basic), a simple form is shown which submits to the searchmysite.net
// search page, restricted to the domain.
// See https://searchmysite.net/pages/documentation/#adding-a-search-box
(function () {
	'use strict';

	// document.currentScript is only valid during synchronous execution, so read it first
	var script = document.currentScript;
	if (!script) {
		return;
	}
	var domain = (script.getAttribute('data-domain') || '').trim().toLowerCase();
	if (!domain) {
		console.warn('sms-search.js: missing data-domain attribute');
		return;
	}
	// Derive the base URL from the script's own src, so this also works with self-hosted instances
	var baseUrl = script.src.replace(/\/static\/js\/sms-search\.js(\?.*)?$/, '');

	// Minimal scoped styling - the host site can override these
	var style = document.createElement('style');
	style.id = 'sms-search-style';
	style.textContent = [
		'.sms-search{font-family:inherit;max-width:40em}',
		'.sms-search-form{display:flex;gap:0.5em;margin:0.5em 0}',
		'.sms-search-input{flex:1;padding:0.4em;font-size:1em;font-family:inherit;box-sizing:border-box}',
		'.sms-search-button{padding:0.4em 1em;font-size:1em;font-family:inherit;cursor:pointer}',
		'.sms-search-results{list-style:none;margin:0.5em 0;padding:0}',
		'.sms-search-result{margin:0.75em 0}',
		'.sms-search-result a{color:inherit}',
		'.sms-search-result-desc{display:block;font-size:0.9em;opacity:0.75}',
		'.sms-search-status{margin:0.5em 0;font-size:0.9em;opacity:0.75}',
		'.sms-search-credit{margin:0.25em 0 0.5em;font-size:0.85em;opacity:0.6}'
	].join('');
	if (!document.getElementById('sms-search-style')) {
		document.head.appendChild(style);
	}

	// Container inserted at the script tag's position
	var container = document.createElement('div');
	container.className = 'sms-search';
	script.parentNode.insertBefore(container, script.nextSibling);

	// Form shared by both modes
	function createForm() {
		var form = document.createElement('form');
		form.className = 'sms-search-form';
		var input = document.createElement('input');
		input.type = 'search';
		input.name = 'q';
		input.className = 'sms-search-input';
		input.placeholder = 'Search';
		input.setAttribute('aria-label', 'Search ' + domain);
		var button = document.createElement('button');
		button.type = 'submit';
		button.className = 'sms-search-button';
		button.textContent = 'Search';
		form.appendChild(input);
		form.appendChild(button);
		container.appendChild(form);
		return { form: form, input: input };
	}

	// Small credit line shown under the search box
	function addCredit() {
		var credit = document.createElement('p');
		credit.className = 'sms-search-credit';
		credit.textContent = 'Powered by ';
		var link = document.createElement('a');
		link.href = 'https://searchmysite.net/';
		link.textContent = 'searchmysite.net';
		link.target = '_blank';
		link.rel = 'noopener';
		credit.appendChild(link);
		container.appendChild(credit);
	}

	// Basic mode: form which submits to the searchmysite.net search page
	function addBasicMode() {
		var parts = createForm();
		parts.form.action = baseUrl + '/search/';
		parts.form.method = 'get';
		var hidden = document.createElement('input');
		hidden.type = 'hidden';
		hidden.name = 'domain';
		hidden.value = domain;
		parts.form.appendChild(hidden);
		addCredit();
	}

	// API mode: fetch the site specific API and render the results on this page
	function addApiMode() {
		var parts = createForm();
		var results = document.createElement('ul');
		results.className = 'sms-search-results';
		var statusEl = document.createElement('p');
		statusEl.className = 'sms-search-status';
		container.appendChild(results);
		container.appendChild(statusEl);

		function clearResults() {
			while (results.firstChild) {
				results.removeChild(results.firstChild);
			}
			statusEl.textContent = '';
		}

		function renderResults(data) {
			clearResults();
			if (!data.results || data.results.length === 0) {
				statusEl.textContent = 'No results.';
				return;
			}
			data.results.forEach(function (result) {
				var li = document.createElement('li');
				li.className = 'sms-search-result';
				var link = document.createElement('a');
				link.href = result.url;
				link.textContent = result.title || result.url;
				li.appendChild(link);
				if (result.description) {
					var desc = document.createElement('span');
					desc.className = 'sms-search-result-desc';
					desc.textContent = result.description;
					li.appendChild(desc);
				}
				results.appendChild(li);
			});
		}

		function doSearch(query) {
			clearResults();
			statusEl.textContent = 'Searching…';
			fetch(baseUrl + '/api/v1/search/' + encodeURIComponent(domain) + '?q=' + encodeURIComponent(query) + '&resultsperpage=10')
				.then(function (response) {
					if (!response.ok) {
						throw new Error('HTTP ' + response.status);
					}
					return response.json();
				})
				.then(renderResults)
				.catch(function () {
					statusEl.textContent = 'Sorry, the search failed. Please try again later.';
				});
			// Keep the query in the URL so results can be deep-linked
			try {
				var url = new URL(window.location.href);
				if (query) {
					url.searchParams.set('q', query);
				} else {
					url.searchParams.delete('q');
				}
				window.history.replaceState({}, '', url);
			} catch (e) {
				// e.g. file: URLs - deep links just won't work
			}
		}

		parts.form.addEventListener('submit', function (event) {
			event.preventDefault();
			var query = parts.input.value.trim();
			if (query) {
				doSearch(query);
			} else {
				clearResults();
			}
		});

		// Run an initial search if the host page URL already has a q, e.g. /search/?q=foo
		var initialQuery = new URLSearchParams(window.location.search).get('q');
		if (initialQuery) {
			parts.input.value = initialQuery;
			doSearch(initialQuery);
		}
	}

	fetch(baseUrl + '/api/v1/status/' + encodeURIComponent(domain))
		.then(function (response) {
			if (!response.ok) {
				throw new Error('HTTP ' + response.status);
			}
			return response.json();
		})
		.then(function (data) {
			if (data.api_enabled) {
				addApiMode();
			} else {
				addBasicMode();
			}
		})
		.catch(function () {
			// Domain not listed, or the status lookup failed - fall back to the simple form
			addBasicMode();
		});
})();
