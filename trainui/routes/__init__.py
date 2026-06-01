"""Blueprint registry for the trainui Flask app."""


def register_blueprints(app) -> None:
    from trainui.routes.core import bp_core
    from trainui.routes.config import bp_config
    from trainui.routes.prompts import bp_prompts
    from trainui.routes.regression import bp_regression
    from trainui.routes.rewrite import bp_rewrite
    from trainui.routes.misc import bp_misc

    for bp in (bp_core, bp_config, bp_prompts, bp_regression, bp_rewrite, bp_misc):
        app.register_blueprint(bp)
