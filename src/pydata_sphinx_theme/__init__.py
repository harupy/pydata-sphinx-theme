"""Bootstrap-based sphinx theme from the PyData community."""

import json
import os
from pathlib import Path
from typing import Dict
from urllib.parse import urlparse

import requests
from requests.exceptions import ConnectionError, HTTPError, RetryError
from sphinx.application import Sphinx
from sphinx.errors import ExtensionError
from sphinx.util import logging

from . import edit_this_page, logo, pygment, short_link, toctree, translator, utils

__version__ = "0.14.2dev0"

logger = logging.getLogger(__name__)


def update_config(app):
    """Update config with new default values and handle deprecated keys."""
    # By the time `builder-inited` happens, `app.builder.theme_options` already exists.
    # At this point, modifying app.config.html_theme_options will NOT update the
    # page's HTML context (e.g. in jinja, `theme_keyword`).
    # To do this, you must manually modify `app.builder.theme_options`.
    theme_options = utils.get_theme_options_dict(app)

    # TODO: deprecation; remove after 0.14 release
    if theme_options.get("logo_text"):
        logo = theme_options.get("logo", {})
        logo["text"] = theme_options.get("logo_text")
        theme_options["logo"] = logo
        logger.warning(
            "The configuration `logo_text` is deprecated." "Use `'logo': {'text': }`."
        )

    # TODO: DEPRECATE after 0.14
    if theme_options.get("footer_items"):
        theme_options["footer_start"] = theme_options.get("footer_items")
        logger.warning(
            "`footer_items` is deprecated. Use `footer_start` or `footer_end` instead."
        )

    # TODO: DEPRECATE after v0.15
    if theme_options.get("favicons"):
        logger.warning(
            "The configuration `favicons` is deprecated."
            "Use the sphinx-favicon extension instead."
        )

    # TODO: in 0.15, set the default navigation_with_keys value to False and remove this deprecation notice
    if theme_options.get("navigation_with_keys", None) is None:
        logger.warning(
            "The default value for `navigation_with_keys` will change to `False` in "
            "the next release. If you wish to preserve the old behavior for your site, "
            "set `navigation_with_keys=True` in the `html_theme_options` dict in your "
            "`conf.py` file."
            "Be aware that `navigation_with_keys = True` has negative accessibility implications:"
            "https://github.com/pydata/pydata-sphinx-theme/issues/1492"
        )
        theme_options["navigation_with_keys"] = False

    # Validate icon links
    if not isinstance(theme_options.get("icon_links", []), list):
        raise ExtensionError(
            "`icon_links` must be a list of dictionaries, you provided "
            f"type {type(theme_options.get('icon_links'))}."
        )

    # Set the anchor link default to be # if the user hasn't provided their own
    if not utils.config_provided_by_user(app, "html_permalinks_icon"):
        app.config.html_permalinks_icon = "#"

    # check the validity of the theme switcher file
    is_dict = isinstance(theme_options.get("switcher"), dict)
    should_test = theme_options.get("check_switcher", True)
    if is_dict and should_test:
        theme_switcher = theme_options.get("switcher")

        # raise an error if one of these compulsory keys is missing
        json_url = theme_switcher["json_url"]
        theme_switcher["version_match"]

        # try to read the json file. If it's a url we use request,
        # else we simply read the local file from the source directory
        # display a log warning if the file cannot be reached
        reading_error = None
        if urlparse(json_url).scheme in ["http", "https"]:
            try:
                request = requests.get(json_url)
                request.raise_for_status()
                content = request.text
            except (ConnectionError, HTTPError, RetryError) as e:
                reading_error = repr(e)
        else:
            try:
                content = Path(app.srcdir, json_url).read_text()
            except FileNotFoundError as e:
                reading_error = repr(e)

        if reading_error is not None:
            logger.warning(
                f'The version switcher "{json_url}" file cannot be read due to the following error:\n'
                f"{reading_error}"
            )
        else:
            # check that the json file is not illformed,
            # throw a warning if the file is ill formed and an error if it's not json
            switcher_content = json.loads(content)
            missing_url = any(["url" not in e for e in switcher_content])
            missing_version = any(["version" not in e for e in switcher_content])
            if missing_url or missing_version:
                logger.warning(
                    f'The version switcher "{json_url}" file is malformed'
                    ' at least one of the items is missing the "url" or "version" key'
                )

    # Add an analytics ID to the site if provided
    analytics = theme_options.get("analytics", {})
    if analytics:
        # Plausible analytics
        plausible_domain = analytics.get("plausible_analytics_domain")
        plausible_url = analytics.get("plausible_analytics_url")

        # Ref: https://plausible.io/docs/plausible-script
        if plausible_domain and plausible_url:
            kwargs = {
                "loading_method": "defer",
                "data-domain": plausible_domain,
                "filename": plausible_url,
            }
            app.add_js_file(**kwargs)

        # Google Analytics
        gid = analytics.get("google_analytics_id")
        if gid:
            gid_js_path = f"https://www.googletagmanager.com/gtag/js?id={gid}"
            gid_script = f"""
                window.dataLayer = window.dataLayer || [];
                function gtag(){{ dataLayer.push(arguments); }}
                gtag('js', new Date());
                gtag('config', '{gid}');
            """

            # Link the JS files
            app.add_js_file(gid_js_path, loading_method="async")
            app.add_js_file(None, body=gid_script)

    # Update ABlog configuration default if present
    fa_provided = utils.config_provided_by_user(app, "fontawesome_included")
    if "ablog" in app.config.extensions and not fa_provided:
        app.config.fontawesome_included = True

    # Handle icon link shortcuts
    shortcuts = [
        ("twitter_url", "fa-brands fa-square-twitter", "Twitter"),
        ("bitbucket_url", "fa-brands fa-bitbucket", "Bitbucket"),
        ("gitlab_url", "fa-brands fa-square-gitlab", "GitLab"),
        ("github_url", "fa-brands fa-square-github", "GitHub"),
    ]
    # Add extra icon links entries if there were shortcuts present
    # TODO: Deprecate this at some point in the future?
    icon_links = theme_options.get("icon_links", [])
    for url, icon, name in shortcuts:
        if theme_options.get(url):
            # This defaults to an empty list so we can always insert
            icon_links.insert(
                0,
                {
                    "url": theme_options.get(url),
                    "icon": icon,
                    "name": name,
                    "type": "fontawesome",
                },
            )
    theme_options["icon_links"] = icon_links

    # Prepare the logo config dictionary
    theme_logo = theme_options.get("logo")
    if not theme_logo:
        # In case theme_logo is an empty string
        theme_logo = {}
    if not isinstance(theme_logo, dict):
        raise ValueError(f"Incorrect logo config type: {type(theme_logo)}")
    theme_options["logo"] = theme_logo


def update_and_remove_templates(
    app: Sphinx, pagename: str, templatename: str, context, doctree
) -> None:
    """Update template names and assets for page build."""
    # Allow for more flexibility in template names
    template_sections = [
        "theme_navbar_start",
        "theme_navbar_center",
        "theme_navbar_persistent",
        "theme_navbar_end",
        "theme_article_header_start",
        "theme_article_header_end",
        "theme_article_footer_items",
        "theme_content_footer_items",
        "theme_footer_start",
        "theme_footer_center",
        "theme_footer_end",
        "theme_secondary_sidebar_items",
        "theme_primary_sidebar_end",
        "sidebars",
    ]
    for section in template_sections:
        if context.get(section):
            # Break apart `,` separated strings so we can use , in the defaults
            if isinstance(context.get(section), str):
                context[section] = [
                    ii.strip() for ii in context.get(section).split(",")
                ]

            # Add `.html` to templates with no suffix
            for ii, template in enumerate(context.get(section)):
                if not os.path.splitext(template)[1]:
                    context[section][ii] = template + ".html"

            # If this is the page TOC, check if it is empty and remove it if so
            def _remove_empty_templates(tname):
                # These templates take too long to render, so skip them.
                # They should never be empty anyway.
                SKIP_EMPTY_TEMPLATE_CHECKS = ["sidebar-nav-bs.html", "navbar-nav.html"]
                if not any(tname.endswith(temp) for temp in SKIP_EMPTY_TEMPLATE_CHECKS):
                    # Render the template and see if it is totally empty
                    rendered = app.builder.templates.render(tname, context)
                    if len(rendered.strip()) == 0:
                        return False
                return True

            context[section] = list(filter(_remove_empty_templates, context[section]))

    # Remove a duplicate entry of the theme CSS. This is because it is in both:
    # - theme.conf
    # - manually linked in `webpack-macros.html`
    if "css_files" in context:
        theme_css_name = "_static/styles/pydata-sphinx-theme.css"
        if theme_css_name in context["css_files"]:
            context["css_files"].remove(theme_css_name)

    # Add links for favicons in the topbar
    for favicon in context.get("theme_favicons", []):
        icon_type = Path(favicon["href"]).suffix.strip(".")
        opts = {
            "rel": favicon.get("rel", "icon"),
            "sizes": favicon.get("sizes", "16x16"),
            "type": f"image/{icon_type}",
        }
        if "color" in favicon:
            opts["color"] = favicon["color"]
        # Sphinx will auto-resolve href if it's a local file
        app.add_css_file(favicon["href"], **opts)

    # Add metadata to DOCUMENTATION_OPTIONS so that we can re-use later
    # Pagename to current page
    app.add_js_file(None, body=f"DOCUMENTATION_OPTIONS.pagename = '{pagename}';")
    if isinstance(context.get("theme_switcher"), dict):
        theme_switcher = context["theme_switcher"]
        json_url = theme_switcher["json_url"]
        version_match = theme_switcher["version_match"]

        # Add variables to our JavaScript for re-use in our main JS script
        js = f"""
        DOCUMENTATION_OPTIONS.theme_version = '{__version__}';
        DOCUMENTATION_OPTIONS.theme_switcher_json_url = '{json_url}';
        DOCUMENTATION_OPTIONS.theme_switcher_version_match = '{version_match}';
        DOCUMENTATION_OPTIONS.show_version_warning_banner = {str(context["theme_show_version_warning_banner"]).lower()};
        """
        app.add_js_file(None, body=js)

    # Update version number for the "made with version..." component
    context["theme_version"] = __version__


def setup(app: Sphinx) -> Dict[str, str]:
    """Setup the Sphinx application."""
    here = Path(__file__).parent.resolve()
    theme_path = here / "theme" / "pydata_sphinx_theme"

    app.add_html_theme("pydata_sphinx_theme", str(theme_path))

    app.add_post_transform(short_link.ShortenLinkTransform)

    app.connect("builder-inited", translator.setup_translators)
    app.connect("builder-inited", update_config)
    app.connect("html-page-context", edit_this_page.setup_edit_url)
    app.connect("html-page-context", toctree.add_toctree_functions)
    app.connect("html-page-context", update_and_remove_templates)
    app.connect("html-page-context", logo.setup_logo_path)
    app.connect("build-finished", pygment.overwrite_pygments_css)
    app.connect("build-finished", logo.copy_logo_images)

    # https://www.sphinx-doc.org/en/master/extdev/i18n.html#extension-internationalization-i18n-and-localization-l10n-using-i18n-api
    app.add_message_catalog("sphinx", here / "locale")

    # Include component templates
    app.config.templates_path.append(str(theme_path / "components"))

    return {"parallel_read_safe": True, "parallel_write_safe": True}
