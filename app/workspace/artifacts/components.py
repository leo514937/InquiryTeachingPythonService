"""Catalog of optional, versioned interactive teaching components."""
from dataclasses import dataclass
from pydantic import BaseModel, ConfigDict, Field


class ReflectionParameters(BaseModel):
    model_config = ConfigDict(extra='forbid')
    initial_incident_angle_deg: int = Field(default=30, ge=0, le=80)
    show_angle_labels: bool = True


@dataclass(frozen=True)
class ActivityComponent:
    id: str
    version: int
    applicable_artifact: str
    description: str
    parameters: type[BaseModel]
    renderer: str


COMPONENTS = {'light_reflection_v1': ActivityComponent(
    id='light_reflection_v1', version=1, applicable_artifact='Experiment',
    description='光反射实验的可选交互模型', parameters=ReflectionParameters, renderer='ReflectionExperiment')}


def is_known_component(component_id):
    return component_id is None or (isinstance(component_id, str) and (component_id == '' or component_id in COMPONENTS))
