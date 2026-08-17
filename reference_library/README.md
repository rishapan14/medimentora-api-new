# Healthy X-ray Reference Library (Phase 9)

This folder holds **real healthy radiographs** used for educational side-by-side comparison.

**Do not** place drawings, icons, cartoons, or synthetic placeholders here.

Metadata is stored in MySQL table **`reference_xray_library`**. Disk paths are relative to this folder.

## Folder layout

Phase 9 canonical taxonomy:

```
reference_library/
  {body_part}/{projection}/{age_group}/{gender}/{filename}.jpg
```

Admin uploads may also use an optional orientation segment:

```
reference_library/
  {body_part}/{projection}/{age_group}/{gender}/{orientation}/{filename}.jpg
```

Examples:

```
chest/pa/adult/male/chest_pa_adult_male_01.jpg
chest/lateral/adult/unisex/chest_lat_adult_unisex_01.png
hand/ap/adult/unisex/unknown/hand_ap_adult_unisex_01.jpg
knee/lateral/child/unisex/knee_lat_child_unisex_01.jpg
```

### Required metadata

| Field | Notes |
|-------|--------|
| body_part | Chest, Hand, Knee, … |
| projection | AP, PA, Lateral, Oblique, … |
| age_group | Infant, Child, Teen, Adult, Older Adult |
| gender | Male, Female, Unisex, Unknown |
| license | Required |
| source | Required |

## How to add images

### Admin panel (recommended)

1. Sign in as an admin.
2. Open **Reference X-Ray Library** / **Upload Healthy X-Rays**.
3. Upload (single, bulk, or ZIP) with full metadata.
4. Or drop files on disk and click **Sync / Rebuild catalog**.

### Automatic retrieval

The matcher scores active references by body part, projection, age group, and gender (when clinically relevant), then returns the best educational match.

If none are available:

> Healthy educational reference is not yet available for this body part. AI analysis remains available.

## Safety

For educational purposes only. This is not a diagnosis. Please consult a qualified healthcare professional.
