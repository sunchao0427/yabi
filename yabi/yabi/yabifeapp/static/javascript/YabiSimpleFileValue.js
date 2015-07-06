

/**
 * YabiSimpleFileValue
 * create a new file value which represents the path and relevant filename
 */
function YabiSimpleFileValue(path, filename, type) {
  if (!Y.Lang.isArray(path)) {
    path = [path];
  }
  this.pathComponents = path.slice();

  this.path = path.slice();
  this.root = this.path.shift();
  this.filename = filename;
  this.type = 'file';
  if (type !== undefined && type !== null) {
    this.type = type;
  }
  this.isSymlink = false;
}

YabiSimpleFileValue.prototype.toString = function() {
  var optionalSlash = '';
  if (this.type == 'directory') {
    optionalSlash = '/';
  }

  if (Y.Lang.isUndefined(this.root)) {
    return this.filename + optionalSlash;
  }

  if (this.filename === '') {
    return this.root + this.path.join('/') + optionalSlash;
  }

  if (this.path.length === 0) {
    return this.root + this.filename + optionalSlash;
  }

  return this.root + this.path.join('/') + '/' + this.filename + optionalSlash;
};

YabiSimpleFileValue.prototype.isEqual = function(b) {
  //console.log(this + " isEqual? " + b);
  // we don't allow files that have the same filename to be selected,
  // even if they come from different paths
  var equal = true;

  equal = this.pathComponents.join('/') == b.pathComponents.join('/');
  equal = equal && (this.filename == b.filename);

  return equal;
};