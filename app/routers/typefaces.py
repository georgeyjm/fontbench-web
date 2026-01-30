from fastapi import APIRouter, HTTPException

from app.db import SessionDep
from app.models import Font, Typeface


router = APIRouter(prefix='/api/typefaces', tags=['typefaces'])


@router.get('', tags=['typefaces'])
async def list_typefaces(db: SessionDep):
    '''List all available typefaces.'''
    typefaces = db.query(Typeface).order_by(Typeface.name).all()
    return {'typefaces': [t.serialize() for t in typefaces]}


@router.get('/{typeface_id}', tags=['typefaces'])
async def get_typeface(db: SessionDep, typeface_id: int, include_fonts: bool = False):
    '''Get a typeface by ID.'''
    typeface = db.query(Typeface).filter(Typeface.id == typeface_id).first()
    if not typeface:
        raise HTTPException(status_code=404, detail='Typeface not found')
    return typeface.serialize(include_fonts=include_fonts)


@router.delete('/{typeface_id}', tags=['typefaces'])
async def delete_typeface(typeface_id: int, db: SessionDep):
    '''Delete a typeface and all its fonts.'''
    typeface = db.query(Typeface).filter(Typeface.id == typeface_id).first()
    if not typeface:
        raise HTTPException(status_code=404, detail='Typeface not found')
    db.delete(typeface)
    db.commit()
    return {'status': 'deleted'}


@router.get('/fonts', tags=['fonts'])
async def list_fonts(db: SessionDep, typeface_id: int | None = None):
    '''List all fonts, optionally filtered by typeface.'''
    query = db.query(Font)
    if typeface_id:
        query = query.filter(Font.typeface_id == typeface_id)
    fonts = query.order_by(Font.created_at.desc()).all()
    return {'fonts': [f.serialize() for f in fonts]}


@router.get('/fonts/{font_id}', tags=['fonts'])
async def get_font(db: SessionDep, font_id: int, include_metrics: bool = False):
    '''Get a font by ID.'''
    font = db.query(Font).filter(Font.id == font_id).first()
    if not font:
        raise HTTPException(status_code=404, detail='Font not found')
    return font.serialize(include_metrics=include_metrics)


# @router.patch('/fonts/{font_id}/typeface', tags=['fonts'])
# async def assign_font_to_typeface(db: SessionDep, font_id: int, typeface_id: int = Form(...)):
#     '''Assign a font to a typeface.'''
#     font = db.query(Font).filter(Font.id == font_id).first()
#     if not font:
#         raise HTTPException(status_code=404, detail='Font not found')

#     typeface = db.query(Typeface).filter(Typeface.id == typeface_id).first()
#     if not typeface:
#         raise HTTPException(status_code=404, detail='Typeface not found')

#     font.typeface_id = typeface_id
#     db.commit()
#     return font.serialize()


@router.delete('/fonts/{font_id}', tags=['fonts'])
async def delete_font(font_id: int, db: SessionDep):
    '''Delete a font and all its computed metrics.'''
    font = db.query(Font).filter(Font.id == font_id).first()
    if not font:
        raise HTTPException(status_code=404, detail='Font not found')
    db.delete(font)
    db.commit()
    return {'status': 'deleted'}
