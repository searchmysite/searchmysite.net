// Get Stripe publishable key
fetch(checkout_config)
.then((result) => { return result.json(); })
.then((data) => {
	// Initialize Stripe.js
	const stripe = Stripe(data.publicKey);
	// Event handler
	document.querySelector("#submitBtn").addEventListener("click", () => {
		// Get Checkout Session ID
		fetch(checkout_url)
		.then((result) => { return result.json(); })
		.then((data) => {
		console.log(data);
		// Redirect to Stripe Checkout
		return stripe.redirectToCheckout({sessionId: data.sessionId})
		})
		.then((res) => {
		console.log(res);
		});
	});
});
