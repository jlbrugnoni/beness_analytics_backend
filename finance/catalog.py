"""One-time starting catalog. Saved company categories remain editable database records."""
from .models import Category, ConfigurationChange

CATALOG_VERSION = 'beness-v1'
# Stable keys allow comparison across independently maintained company catalogs.
# Names preserve the client workbook; no financial source rows are included.
# Child codes are permanent identifiers: never renumber or reuse them when changing names/order.
CATALOG = [('personal',
  'Personal',
  [('01', 'Sueldos'),
   ('02', 'Seguridad social'),
   ('03', 'Honorarios'),
   ('04', 'Comisiones'),
   ('05', 'Vacaciones / liquidaciones'),
   ('06', 'Dietas y Viaticos')]),
 ('local',
  'Local / Instalaciones',
  [('01', 'Alquiler'), ('02', 'Comunidad'), ('03', 'Mantenimiento'), ('04', 'Limpieza'), ('05', 'Seguro')]),
 ('servicios',
  'Servicios',
  [('01', 'Electricidad'),
   ('02', 'Agua'),
   ('03', 'Internet y telefono'),
   ('04', 'Valet parking'),
   ('05', 'Otros')]),
 ('operacion',
  'Operacion',
  [('01', 'Equipamiento'),
   ('02', 'Mantenimiento equipos'),
   ('03', 'Materiales'),
   ('04', 'Insumos'),
   ('05', 'Uniformes')]),
 ('marketing',
  'Marketing',
  [('01', 'Publicidad digital'), ('02', 'Diseño'), ('03', 'Impresiones'), ('04', 'Promociones')]),
 ('software', 'Software', [('01', 'Mindbody'), ('02', 'Alegra'), ('03', 'Otras suscripciones')]),
 ('administracion',
  'Administracion',
  [('01', 'Contabilidad'),
   ('02', 'Legal'),
   ('03', 'Impuestos'),
   ('04', 'Sueldos administración'),
   ('05', 'Seguridad social administración'),
   ('06', 'Transporte administración'),
   ('07', 'Caja chica administración'),
   ('08', 'Otros gastos administración')]),
 ('bancos', 'Bancos', [('01', 'Comisiones'), ('02', 'TPV / POS'), ('03', 'Intereses'), ('04', 'Devoluciones')]),
 ('logistica', 'Logistica', [('01', 'Envios'), ('02', 'Transporte'), ('03', 'Aduanas')]),
 ('otros', 'Otros', [('01', 'Varios'), ('02', 'Extraordinarios')])]


def create_starting_catalog(company, actor):
    """Caller holds the company lock, checks permissions/empty catalog and wraps a transaction."""
    from .serializers import CategorySerializer
    created = 0
    for code, name, names in CATALOG:
        parent = Category.objects.create(company=company, name=name, catalog_code=code,
            default_treatment='operating', default_allocation='administration' if code == 'administracion' else 'direct',
            sensitive=code == 'personal')
        items = [parent]
        for child_code, child_name in names:
            treatment = ''
            if (code, child_name) in {('operacion', 'Equipamiento'), ('bancos', 'Intereses'), ('bancos', 'Devoluciones')}:
                treatment = 'review'
            elif (code, child_name) in {('administracion', 'Impuestos'), ('otros', 'Extraordinarios')}:
                treatment = 'extraordinary'
            items.append(Category.objects.create(company=company, parent=parent, name=child_name,
                catalog_code=f'{code}-{child_code}', default_treatment=treatment, default_allocation='',
                sensitive=code == 'administracion' and child_name in {'Sueldos administración', 'Seguridad social administración'}))
        for category in items:
            # No request context: caller-specific permission hints do not belong in history.
            data = dict(CategorySerializer(category).data)
            data.pop('can_edit'); data.pop('can_add_child')
            ConfigurationChange.objects.create(actor=actor, target_type='category', target_id=category.pk,
                target_label=category.name, before={}, after=data)
            created += 1
    return created
