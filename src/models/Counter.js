import mongoose from 'mongoose';

const counterSchema = new mongoose.Schema({
  _id: { type: String, required: true },
  value: { type: Number, required: true, default: 0 },
}, { versionKey: false });

export const Counter = mongoose.model('Counter', counterSchema);

export async function nextLegacyId(name) {
  const counter = await Counter.findByIdAndUpdate(name, { $inc: { value: 1 } }, {
    new: true, upsert: true, setDefaultsOnInsert: true,
  });
  return counter.value;
}
