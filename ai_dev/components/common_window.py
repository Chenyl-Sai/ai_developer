
class CommonWindow:

    def __init__(self, **kwargs):
        self.app = None
        self.cli = kwargs['cli']

    def set_app(self, app):
        self.app = app

    def refresh(self):
        if self.app:
            try:
                self.app.invalidate()
            except:
                pass

    def need_show(self):
        return True