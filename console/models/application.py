"""Application model for TCM Console."""

from pydantic import BaseModel, Field


class Application(BaseModel):
    """Application configuration — owns WAR identity."""

    app_id: str = Field(description="Unique application identifier, e.g. 'app-a'")
    name: str = Field(description="Human-readable application name, e.g. 'BrokerageMobileWeb'")
    war_filename: str = Field(
        description="Canonical WAR filename written to webapps/, e.g. 'BrokerageMobileWeb.war'"
    )
    context_path: str = Field(description="Tomcat context path, e.g. '/BMW'")
