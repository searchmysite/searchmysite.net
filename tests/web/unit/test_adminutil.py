from searchmysite.adminutils import extract_domain

# Might also want to test domain_allowing_subdomains, e.g. user.github.io
# That would require initialising tblSettings accordingly
def test_extract_domain(anon_client):
    domain = extract_domain("https://www.michael-lewis.com/")
    assert domain == "michael-lewis.com"