import { nextLegacyId } from '../Counter.js';

export function legacyIdPlugin(schema, options = {}) {
  schema.add({ id: { type: Number, unique: true, index: true } });
  schema.pre('save', async function assignLegacyId() {
    if (this.isNew && this.id == null) this.id = await nextLegacyId(options.name ?? this.constructor.modelName);
  });
}
