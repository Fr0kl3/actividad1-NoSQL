db = db.getSiblingDB('tienda');

db.usuarios.insertMany([
  { username: 'alice', password: 'alice123', nombre: 'Alice', rol: 'cliente' },
  { username: 'bob',   password: 'bob123',   nombre: 'Bob',   rol: 'cliente' },
  { username: 'admin', password: 'admin123', nombre: 'Admin', rol: 'admin' }
]);

db.pedidos.insertMany([
  { producto: 'Teclado mecánico',   cantidad: 1 },
  { producto: 'Ratón inalámbrico',  cantidad: 2 },
  { producto: 'Monitor 27 pulgadas', cantidad: 1 }
]);
