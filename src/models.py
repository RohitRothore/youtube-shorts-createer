from pydantic import BaseModel, Field


class Scene(BaseModel):
    narration: str = Field(description="Spoken text for this scene")
    visual_prompt: str = Field(description="Image generation prompt for this scene")
    on_screen_text: str = Field(default="", description="Optional bold text overlay")


class ShortScript(BaseModel):
    title: str
    hook: str = Field(description="Opening line to grab attention in first 2 seconds")
    scenes: list[Scene]
    hashtags: list[str] = Field(default_factory=list)
