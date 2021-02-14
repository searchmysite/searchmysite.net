# How to contribute 

Thanks for reading this far. Contributions of all types are welcome, from reporting issues, to suggesting improvements, or implementing fixes or enhancements. This document lays out some rough guidelines for how to do so. It is fairly brief as it is a new project, but more detail will be added here over time if necessary.


## Reporting issues and suggesting improvements

The issue list is at [https://github.com/searchmysite/searchmysite.net/issues](https://github.com/searchmysite/searchmysite.net/issues).

If you encounter a bug or other issue, please log it there. It will help improve the service for everyone. If possible, please try to check there isn't already one logged for that issue.

If you've a small change you'd like to suggest, feel free to log directly in the issues list. If it is a big change, it would be best to have an offline discussion about it first.


## Implementing fixes or enhancements  

### Creating pull requests

Pull requests will generally only be accepted if they relate to an already logged and commented upon issue. Each pull request should relate to one feature or issue, rather than a combination.

If you are granted write access to the main repository, please use feature branches for each issue.

### Coding conventions

Pretty much all of the custom code is in Python. Coding standards broadly follow the [PEP 8 Style Guide](https://www.python.org/dev/peps/pep-0008/), with the main exception being the maximum line length.

Generally less code is better, unless brevity comes at the expense of readability.

### Testing

Changes should be accompanied by test cases if possible.

Code coverage isn't great at the moment, and there are some issues with testing, e.g. they are [run in Flask rather than Apache + mod_wsgi](https://github.com/searchmysite/searchmysite.net/issues/23) and just [run the indexer process](https://github.com/searchmysite/searchmysite.net/issues/24), but this should improve over time.


## Other sources of information

See also:
- [Blog](https://blog.searchmysite.net/) - contains a number of posts covering the project's aims, objectives, and other topics, often aimed at a slightly less technical but broader audience.
- [Documentation](https://searchmysite.net/pages/documentation/) - contains FAQ, information on the query syntax, fields, indexing, relevancy tuning and API.
- [README](https://github.com/searchmysite/searchmysite.net/blob/main/README.md) - contains information on how to set up your development environment, and make and test changes.
- Comments in source code. There aren't a lot, but hopefully the tricky parts are explained and important requirements highlighted. 


## Community behaviour

See e.g. the [Python code of conduct](https://www.python.org/psf/conduct/). Please be respectful of other people. This is a spare-time side-project, and other contributors will likely be offering their time for free. Plus it is trying to [make the internet a better place](https://blog.searchmysite.net/posts/searchmysite.net-building-a-simple-search-for-non-commercial-websites/), so should be attracting good people.

