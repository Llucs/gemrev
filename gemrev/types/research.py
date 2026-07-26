class DeepResearchPlan:
    def __init__(self, research_id=None, title=None, query=None, steps=None,
                 eta_text=None, confirm_prompt=None, modify_prompt=None,
                 confirmation_url=None, metadata=None, cid=None,
                 response_text=None, raw_state=None):
        self.research_id = research_id
        self.title = title
        self.query = query
        self.steps = steps or []
        self.eta_text = eta_text
        self.confirm_prompt = confirm_prompt
        self.modify_prompt = modify_prompt
        self.confirmation_url = confirmation_url
        self.metadata = metadata or []
        self.cid = cid
        self.response_text = response_text
        self.raw_state = raw_state


class DeepResearchStatus:
    def __init__(self, research_id=None, state='running', title=None, query=None,
                 cid=None, notes=None, done=False, raw_state=None, raw=None):
        self.research_id = research_id
        self.state = state
        self.title = title
        self.query = query
        self.cid = cid
        self.notes = notes or []
        self.done = done
        self.raw_state = raw_state
        self.raw = raw


class DeepResearchResult:
    def __init__(self, plan=None, start_output=None, final_output=None,
                 statuses=None, done=False):
        self.plan = plan
        self.start_output = start_output
        self.final_output = final_output
        self.statuses = statuses or []
        self.done = done

    @property
    def text(self):
        return self.final_output.text if self.final_output else ''
