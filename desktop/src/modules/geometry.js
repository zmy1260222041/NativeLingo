function positiveNumber(value) {
  const number = Number(value);
  return Number.isFinite(number) && number > 0 ? number : 0;
}

export function containRect(frameWidth, frameHeight, mediaWidth, mediaHeight) {
  const width = positiveNumber(frameWidth);
  const height = positiveNumber(frameHeight);
  const sourceWidth = positiveNumber(mediaWidth);
  const sourceHeight = positiveNumber(mediaHeight);
  if (!width || !height || !sourceWidth || !sourceHeight) {
    return { x: 0, y: 0, width: 0, height: 0, scale: 0 };
  }

  const scale = Math.min(width / sourceWidth, height / sourceHeight);
  const fittedWidth = sourceWidth * scale;
  const fittedHeight = sourceHeight * scale;
  return {
    x: (width - fittedWidth) / 2,
    y: (height - fittedHeight) / 2,
    width: fittedWidth,
    height: fittedHeight,
    scale,
  };
}

export function objectsAtPoint(objects, x, y) {
  return (objects || [])
    .filter((object) => {
      if (!Array.isArray(object.box) || object.box.length !== 4) return false;
      const [left, top, width, height] = object.box.map(Number);
      if (![left, top, width, height].every(Number.isFinite)) return false;
      return x >= left && x <= left + width && y >= top && y <= top + height;
    })
    .sort((first, second) => {
      const firstArea = Number(first.box[2]) * Number(first.box[3]);
      const secondArea = Number(second.box[2]) * Number(second.box[3]);
      return firstArea - secondArea;
    });
}
