"""Small mobile projections; never send model secrets to the mobile picker."""
from fastapi import APIRouter, Depends
from agentscope.app.access import ResourceKind
from agentscope.app.deps import get_current_user_id, get_resource_access_service

router = APIRouter(prefix='/mobile', tags=['Mobile'])


@router.get('/credentials')
async def credential_choices(user_id: str = Depends(get_current_user_id),
                             access=Depends(get_resource_access_service)):
    entries = await access.list_resource(user_id, ResourceKind.CREDENTIAL)
    return {'credentials': [{'id': entry.id, 'name': entry.data.get('name', ''),
                             'type': entry.data.get('type', '')} for entry in entries]}
